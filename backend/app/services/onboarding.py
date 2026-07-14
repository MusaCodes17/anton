"""
New-Retailer Onboarding service (R4.6, from MAINTENANCE_PLAN I1).

Takes a retailer from "row in the DB with no working scraper" to either
"scraping" or "honestly declared unscrapable", reusing the pieces that already
exist:

- `platform_detection.determine_platform` — the Shopify/Algolia sniff.
- the scrapability dry-run (`ScrapeOrchestrator.test_shoe_scrapability`'s
  per-retailer search) — here run against a *candidate* scraper built from the
  proposed platform/config, so a not-yet-enabled retailer can be tested.
- `scrape_history.scrape_health` — which now surfaces `needs_onboarding` so the
  R4.5 watchdog and this share one health view (a retailer with no scraper is a
  known gap, not a "quietly broken" scraper the watchdog should nag about).

Write paths are narrow and confirmation-gated (CLAUDE.md §2/§4.4, INV-8):
`apply_onboarding` (wire up a detected platform) and `mark_unscrapable` (record
the Sporting-Life-style verdict on the row) are the *only* functions here that
write. Detection and probing are read-only.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Retailer, Shoe
from app.scrapers.platform_detection import (
    PLATFORMS,
    PlatformDetectionError,
    determine_platform,
    has_algolia_credentials,
)
from app.scrapers.registry import BESPOKE_SCRAPERS, build_dynamic_scraper

logger = logging.getLogger(__name__)

# Default shoe used for the dry-run search when the watchlist is empty — a
# ubiquitous model most running retailers stock, so a zero-result is a signal
# about the *scraper*, not an obscure query.
_FALLBACK_SAMPLE = ("Nike", "Pegasus")


def _is_unscrapable(retailer: Retailer) -> bool:
    """A retailer explicitly recorded as unscrapable (the Sporting Life precedent)."""
    return bool((retailer.scraper_config or {}).get("unscrapable"))


def _has_working_scraper(retailer: Retailer) -> bool:
    """
    True when *some* scraper can already run for this retailer, without
    instantiating one (construction is cheap but this stays purely inspective):
    a hand-written bespoke subclass by name, a Shopify platform (needs no
    config), or an Algolia platform with its credentials present.
    """
    if retailer.name in BESPOKE_SCRAPERS:
        return True
    if retailer.platform == "shopify":
        return True
    if retailer.platform == "algolia" and has_algolia_credentials(retailer.scraper_config):
        return True
    return False


def _needs_onboarding(retailer: Retailer) -> bool:
    """An active retailer with no working scraper that hasn't been declared unscrapable."""
    return bool(retailer.is_active) and not _has_working_scraper(retailer) and not _is_unscrapable(retailer)


def retailers_needing_onboarding(db: Session) -> list[dict]:
    """
    Active retailers that have no working scraper and haven't been marked
    unscrapable — the onboarding queue. Ordered by name.

    Read-only. Each entry: retailer_id, name, base_url, platform.
    """
    retailers = (
        db.query(Retailer)
        .filter(Retailer.is_active == True)  # noqa: E712
        .order_by(Retailer.name)
        .all()
    )
    return [
        {
            "retailer_id": r.id,
            "name": r.name,
            "base_url": r.base_url,
            "platform": r.platform,
        }
        for r in retailers
        if _needs_onboarding(r)
    ]


def _sample_shoe(db: Session, brand: Optional[str], model: Optional[str]) -> tuple[str, str]:
    """Resolve the shoe used for the dry-run: caller-supplied → first watchlist shoe → fallback."""
    if brand and model:
        return brand.strip(), model.strip()
    shoe = db.query(Shoe).filter(Shoe.is_active == True).order_by(Shoe.id).first()  # noqa: E712
    if shoe:
        return shoe.brand, shoe.model
    return _FALLBACK_SAMPLE


def probe_retailer(
    db: Session,
    retailer_id: int,
    *,
    sample_brand: Optional[str] = None,
    sample_model: Optional[str] = None,
) -> dict:
    """
    Investigate a retailer without writing anything: sniff its platform, and —
    if that yields a generic scraper — dry-run a real search against a candidate
    scraper built from the *proposed* platform/config (not the persisted row).

    Returns a findings dict the onboarding prompt reports to the runner before
    any config write:
        detected_platform      "shopify" | "algolia" | "custom"
        proposed_scraper_config dict | None  (what apply_onboarding would store)
        scraping_recommended   bool  (a generic scraper is available)
        sample_shoe            "Brand Model" used for the dry-run
        dry_run                {status, products_found, sample_price, sizes, error?}
                               or None when no candidate scraper could be built
        recommendation         "enable_scraping" | "needs_custom_scraper"
        note                   human-readable summary

    Read-only. `Raises: LookupError` if the retailer does not exist.
    """
    retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()
    if not retailer:
        raise LookupError(f"Retailer with id {retailer_id} not found")

    # Auto-detect: no requested platform, so determine_platform probes the site.
    # Keep any existing scraper_config so pre-filled Algolia creds are honored.
    try:
        detected_platform, _ = determine_platform(
            base_url=retailer.base_url,
            requested_platform=None,
            scraper_config=retailer.scraper_config,
        )
    except PlatformDetectionError as e:
        # Algolia implied-but-incomplete: report it as custom with the reason.
        detected_platform = "custom"
        logger.info(f"Platform detection for '{retailer.name}' fell back to custom: {e}")

    proposed_config = retailer.scraper_config if detected_platform == "algolia" else None

    if detected_platform not in ("shopify", "algolia"):
        return {
            "retailer_id": retailer.id,
            "name": retailer.name,
            "detected_platform": detected_platform,
            "proposed_scraper_config": None,
            "scraping_recommended": False,
            "sample_shoe": None,
            "dry_run": None,
            "recommendation": "needs_custom_scraper",
            "note": (
                f"{retailer.name} is not a recognised Shopify or Algolia storefront. "
                "It needs a bespoke scraper, or should be marked unscrapable if none "
                "is worth building (mark_unscrapable)."
            ),
        }

    # Build a candidate scraper from the *proposed* config on a transient (not
    # session-added) Retailer, so probing never persists a platform change.
    candidate = Retailer(
        name=retailer.name,
        base_url=retailer.base_url,
        platform=detected_platform,
        scraper_config=proposed_config,
    )
    scraper = build_dynamic_scraper(candidate)

    brand, model = _sample_shoe(db, sample_brand, sample_model)
    dry_run: dict = {"status": "not_run", "products_found": 0}
    if scraper is None:
        # Detected algolia but creds missing — determine_platform would have
        # raised, so this is defensive.
        dry_run = None
    else:
        try:
            products = scraper.search_products_filtered(brand, model)
            if products:
                first = products[0]
                sizes = first.get("sizes_available") or []
                sample_price = first.get("price")
                if not sizes:
                    # Shopify's search step omits sizes — the detail call has them.
                    try:
                        details = scraper.get_product_details(first["product_url"])
                        if details:
                            sample_price = details.get("price", sample_price)
                            sizes = details.get("sizes_available") or []
                    except Exception as e:  # pragma: no cover - network edge
                        logger.warning(f"[{retailer.name}] onboarding detail lookup failed: {e}")
                dry_run = {
                    "status": "success",
                    "products_found": len(products),
                    "sample_price": sample_price,
                    "sizes": sizes,
                }
            else:
                dry_run = {
                    "status": "not_found",
                    "products_found": 0,
                    "note": "Scraper ran but found no matches for the sample shoe.",
                }
        except Exception as e:
            logger.warning(f"[{retailer.name}] onboarding dry-run error: {e}")
            dry_run = {"status": "error", "products_found": 0, "error": str(e)}

    found = bool(dry_run and dry_run.get("products_found", 0) > 0)
    return {
        "retailer_id": retailer.id,
        "name": retailer.name,
        "detected_platform": detected_platform,
        "proposed_scraper_config": proposed_config,
        "scraping_recommended": scraper is not None,
        "sample_shoe": f"{brand} {model}",
        "dry_run": dry_run,
        "recommendation": "enable_scraping",
        "note": (
            f"Detected a {detected_platform} storefront and the dry-run "
            f"{'found products' if found else 'returned no products (try a different sample shoe before enabling)'}. "
            "Confirm to wire up the generic scraper (apply_onboarding)."
        ),
    }


def apply_onboarding(
    db: Session,
    retailer_id: int,
    *,
    platform: str,
    scraper_config: Optional[dict] = None,
) -> Retailer:
    """
    The single write path that wires a detected platform onto a retailer:
    sets `platform`, `scraper_config`, and enables scraping. Only for the
    generic-scraper platforms — a bespoke retailer already scrapes, and a
    "custom" outcome goes through `mark_unscrapable` instead.

    Confirmation-gated at the caller (the MCP tool requires confirm=True;
    INV-8): no config is written until the runner approves the probe findings.

    `Raises:`
        LookupError — retailer not found.
        ValueError  — platform not in {"shopify","algolia"}, or Algolia without
                      complete credentials in scraper_config.
    """
    if platform not in ("shopify", "algolia"):
        raise ValueError(
            f"apply_onboarding only wires generic scrapers; platform must be "
            f"'shopify' or 'algolia', got '{platform}'. Use mark_unscrapable for custom."
        )
    if platform not in PLATFORMS:  # defensive; PLATFORMS is the source of truth
        raise ValueError(f"Unknown platform '{platform}'.")

    retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()
    if not retailer:
        raise LookupError(f"Retailer with id {retailer_id} not found")

    if platform == "algolia" and not has_algolia_credentials(scraper_config):
        raise ValueError(
            "Algolia retailers require scraper_config with algolia_app_id, "
            "algolia_api_key, and algolia_index."
        )

    retailer.platform = platform
    # Shopify needs no config; store creds only for Algolia.
    retailer.scraper_config = scraper_config if platform == "algolia" else None
    retailer.scraping_enabled = True
    db.commit()
    db.refresh(retailer)
    logger.info(f"Onboarded retailer '{retailer.name}' as platform={platform}, scraping enabled.")
    return retailer


def mark_unscrapable(db: Session, retailer_id: int, *, reason: str) -> Retailer:
    """
    Record the honest "no scraper worth building" verdict on the row (the
    Sporting Life precedent), so the retailer drops out of the onboarding queue
    and the R4.5 watchdog never nags about it: platform stays "custom", scraping
    is disabled, and `scraper_config.unscrapable`/`unscrapable_reason` are set.

    Confirmation-gated at the caller. `Raises: LookupError` if not found;
    `ValueError` if reason is blank.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A reason is required when marking a retailer unscrapable.")

    retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()
    if not retailer:
        raise LookupError(f"Retailer with id {retailer_id} not found")

    cfg = dict(retailer.scraper_config or {})
    cfg["unscrapable"] = True
    cfg["unscrapable_reason"] = reason
    retailer.scraper_config = cfg
    retailer.platform = "custom"
    retailer.scraping_enabled = False
    db.commit()
    db.refresh(retailer)
    logger.info(f"Marked retailer '{retailer.name}' unscrapable: {reason}")
    return retailer
