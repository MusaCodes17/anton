"""Retailer-onboarding MCP surface: queue, probe, onboard, mark unscrapable."""
from typing import Optional

from pydantic import ValidationError

from app.models.schemas import ScraperConfig
from app.services import onboarding as onboarding_svc
from app.mcp_server import _core
from app.mcp_server._core import mcp


# ---------------------------------------------------------------------------
# R4.6 — New-Retailer Onboarding Agent
# ---------------------------------------------------------------------------

@mcp.tool()
def get_onboarding_queue() -> dict:
    """
    List active retailers that have no working scraper and haven't been marked
    unscrapable — the retailers awaiting onboarding.

    A newly-added retailer starts as platform="custom" with scraping disabled;
    until it's wired to a Shopify/Algolia scraper (or a bespoke one is written),
    it contributes nothing to the deal feed. This is the same list surfaced as
    `needs_onboarding` in scrape_health.

    Each entry: retailer_id, name, base_url, platform. Read-only. For each one,
    call probe_retailer to investigate, then onboard_retailer or
    mark_retailer_unscrapable to resolve it.
    """
    with _core.get_session() as db:
        return {"needs_onboarding": onboarding_svc.retailers_needing_onboarding(db)}


@mcp.tool()
def probe_retailer(
    retailer_id: int,
    sample_brand: Optional[str] = None,
    sample_model: Optional[str] = None,
) -> dict:
    """
    Investigate a retailer's scrapability WITHOUT writing anything: sniff its
    storefront platform (Shopify/Algolia/custom) and, when a generic scraper is
    possible, dry-run a real product search against a candidate scraper built
    from the detected platform.

    Use this before onboard_retailer to gather the evidence the runner needs to
    approve wiring up a scraper. The dry-run uses the first watchlist shoe (or a
    common fallback) unless you pass sample_brand + sample_model.

    Returns detected_platform, proposed_scraper_config, a dry_run result
    (status / products_found / sample_price / sizes), a recommendation
    ("enable_scraping" | "needs_custom_scraper"), and a human-readable note.

    Args:
        retailer_id: the retailer to probe (from get_onboarding_queue).
        sample_brand: optional brand for the dry-run search.
        sample_model: optional model for the dry-run search.
    """
    try:
        with _core.get_session() as db:
            return onboarding_svc.probe_retailer(
                db, retailer_id, sample_brand=sample_brand, sample_model=sample_model
            )
    except LookupError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def onboard_retailer(
    retailer_id: int,
    platform: str,
    confirm: bool,
    scraper_config: Optional[dict] = None,
) -> dict:
    """
    Wire a detected platform onto a retailer and enable scraping — the write
    step of onboarding. CONFIRMATION REQUIRED: call with confirm=False first to
    preview; only pass confirm=True after the runner has approved the
    probe_retailer findings (INV-8 — no config is written without confirmation).

    Only for the generic-scraper platforms: platform must be "shopify" or
    "algolia". A "custom" outcome (no generic scraper fits) goes through
    mark_retailer_unscrapable instead. Algolia requires scraper_config with
    algolia_app_id, algolia_api_key, and algolia_index.

    Args:
        retailer_id: the retailer to onboard.
        platform: "shopify" or "algolia".
        confirm: must be True to write; False returns a preview only.
        scraper_config: Algolia credential payload (ignored for Shopify).
    """
    if not confirm:
        return {
            "success": False,
            "pending_confirmation": True,
            "message": (
                f"Ready to set retailer {retailer_id} to platform={platform} and enable "
                "scraping. Re-call with confirm=True to apply."
            ),
        }
    stored_config = None
    if scraper_config is not None:
        try:
            stored_config = ScraperConfig.model_validate(scraper_config).as_stored()
        except ValidationError as e:
            msg = "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
            return {"success": False, "error": f"Invalid scraper_config: {msg}"}
    try:
        with _core.get_session() as db:
            retailer = onboarding_svc.apply_onboarding(
                db, retailer_id, platform=platform, scraper_config=stored_config
            )
            return {
                "success": True,
                "retailer_id": retailer.id,
                "name": retailer.name,
                "platform": retailer.platform,
                "scraping_enabled": retailer.scraping_enabled,
                "message": f"{retailer.name} onboarded as {retailer.platform}; scraping enabled.",
            }
    except (LookupError, ValueError) as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def mark_retailer_unscrapable(retailer_id: int, reason: str, confirm: bool) -> dict:
    """
    Record the honest "no scraper worth building" verdict on a retailer (the
    Sporting Life precedent): platform stays custom, scraping is disabled, and
    the row is flagged so it drops out of the onboarding queue and the watchdog
    never nags about it.

    CONFIRMATION REQUIRED: pass confirm=True only after the runner agrees the
    retailer isn't worth a scraper (e.g. Cloudflare-gated, or an unbuilt custom
    platform). A `reason` is mandatory and is stored on the row.

    Args:
        retailer_id: the retailer to mark.
        reason: why it's unscrapable (stored as unscrapable_reason).
        confirm: must be True to write; False returns a preview only.
    """
    if not confirm:
        return {
            "success": False,
            "pending_confirmation": True,
            "message": (
                f"Ready to mark retailer {retailer_id} unscrapable ({reason!r}). "
                "Re-call with confirm=True to apply."
            ),
        }
    try:
        with _core.get_session() as db:
            retailer = onboarding_svc.mark_unscrapable(db, retailer_id, reason=reason)
            return {
                "success": True,
                "retailer_id": retailer.id,
                "name": retailer.name,
                "message": f"{retailer.name} marked unscrapable: {reason}",
            }
    except (LookupError, ValueError) as e:
        return {"success": False, "error": str(e)}


@mcp.prompt()
def retailer_onboarding() -> str:
    """Guided workflow to take a newly-added retailer from no-scraper to scraping-or-declared-unscrapable."""
    return """\
You are helping Anton onboard retailers that were added without a working
scraper — taking each from "a row in the DB" to either "scraping" or "honestly
declared unscrapable". Every config write requires the runner's confirmation.

## Steps

1. Call `get_onboarding_queue` to list retailers needing onboarding. If it's
   empty, report that and stop.

2. For each retailer, call `probe_retailer(retailer_id)`. It sniffs the platform
   and dry-runs a real product search. Report per retailer:
   - **Retailer name** and detected_platform
   - The dry_run result: products_found, sample_price, sizes (or the error/
     not_found reason)
   - The recommendation ("enable_scraping" or "needs_custom_scraper")
   If the dry-run found nothing, offer to re-probe with a different
   sample_brand/sample_model (a shoe you know the retailer stocks) before
   concluding.

3. Present a recommendation to the runner and WAIT for confirmation:
   - If recommendation is "enable_scraping" and the dry-run found products:
     propose `onboard_retailer(retailer_id, platform, confirm=True[, scraper_config])`.
     For Shopify, no scraper_config is needed. For Algolia, you must have the
     algolia_app_id / algolia_api_key / algolia_index (from proposed_scraper_config).
   - If recommendation is "needs_custom_scraper" (a custom storefront) and the
     runner decides it isn't worth a bespoke scraper: propose
     `mark_retailer_unscrapable(retailer_id, reason, confirm=True)` with a clear
     reason (e.g. "Cloudflare-gated", "unbuilt custom platform").

4. Only call the write tools with confirm=True after the runner explicitly
   approves. Report the outcome (platform + scraping_enabled, or the unscrapable
   verdict).

## Rules
- Never write config without confirmation (confirm=True) — preview with
  confirm=False first if unsure.
- Don't guess Algolia credentials. If they're absent, the retailer needs a
  bespoke scraper or an unscrapable verdict, not a fabricated config.
- A zero-product dry-run is a signal to retry with a better sample shoe, not an
  automatic "unscrapable" — only mark unscrapable when the platform itself
  can't be scraped.
"""
