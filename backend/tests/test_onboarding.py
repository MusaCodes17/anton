"""
Tests for R4.6 onboarding service — the New-Retailer Onboarding Agent.

Rules verified:
- The onboarding queue = active retailers with no working scraper, not marked
  unscrapable (bespoke / shopify / algolia-with-creds are excluded).
- probe_retailer is read-only and reports the detected platform + dry-run.
- apply_onboarding is the single write path for wiring a generic scraper and
  removes the retailer from the queue; guards custom + credential-less algolia.
- mark_unscrapable records the verdict and removes the retailer from the queue.
- scrape_health surfaces the queue as `needs_onboarding`.
"""
import pytest

from app.models.models import Retailer, Shoe
from app.services import onboarding, scrape_history


def _retailer(db, *, name="New Shop", platform="custom", scraper_config=None,
              is_active=True, scraping_enabled=False, base_url=None):
    r = Retailer(
        name=name,
        base_url=base_url or f"https://{name.replace(' ', '').lower()}.example",
        platform=platform,
        scraper_config=scraper_config,
        is_active=is_active,
        scraping_enabled=scraping_enabled,
    )
    db.add(r)
    db.flush()
    return r


_ALGOLIA_CREDS = {
    "algolia_app_id": "APP",
    "algolia_api_key": "KEY",
    "algolia_index": "products",
}


class _FakeScraper:
    """Stand-in scraper: no network, returns preset search results."""

    def __init__(self, products=None, details=None):
        self._products = products if products is not None else []
        self._details = details

    def search_products_filtered(self, brand, model):
        return self._products

    def get_product_details(self, url):
        return self._details


# --------------------------------------------------------------------------
# retailers_needing_onboarding
# --------------------------------------------------------------------------

def test_custom_retailer_without_scraper_is_in_queue(db):
    _retailer(db, name="Mystery Store", platform="custom")
    queue = onboarding.retailers_needing_onboarding(db)
    assert [r["name"] for r in queue] == ["Mystery Store"]
    assert queue[0]["platform"] == "custom"


def test_shopify_retailer_is_not_in_queue(db):
    _retailer(db, name="Shopify Store", platform="shopify")
    assert onboarding.retailers_needing_onboarding(db) == []


def test_algolia_with_credentials_is_not_in_queue(db):
    _retailer(db, name="Algolia Store", platform="algolia", scraper_config=_ALGOLIA_CREDS)
    assert onboarding.retailers_needing_onboarding(db) == []


def test_algolia_without_credentials_is_in_queue(db):
    _retailer(db, name="Algolia Store", platform="algolia", scraper_config={"algolia_app_id": "APP"})
    assert [r["name"] for r in onboarding.retailers_needing_onboarding(db)] == ["Algolia Store"]


def test_bespoke_retailer_is_not_in_queue(db):
    # SAIL has a hand-written subclass in BESPOKE_SCRAPERS despite platform=custom.
    _retailer(db, name="SAIL", platform="custom")
    assert onboarding.retailers_needing_onboarding(db) == []


def test_unscrapable_retailer_is_not_in_queue(db):
    _retailer(db, name="Sporting Life", platform="custom",
              scraper_config={"unscrapable": True, "unscrapable_reason": "Cloudflare"})
    assert onboarding.retailers_needing_onboarding(db) == []


def test_inactive_retailer_is_not_in_queue(db):
    _retailer(db, name="Closed Store", platform="custom", is_active=False)
    assert onboarding.retailers_needing_onboarding(db) == []


# --------------------------------------------------------------------------
# probe_retailer
# --------------------------------------------------------------------------

def test_probe_missing_retailer_raises(db):
    with pytest.raises(LookupError):
        onboarding.probe_retailer(db, 9999)


def test_probe_custom_platform_recommends_custom_scraper(db, monkeypatch):
    r = _retailer(db, name="Weird Store", platform="custom")
    monkeypatch.setattr(onboarding, "determine_platform", lambda **kw: ("custom", False))
    result = onboarding.probe_retailer(db, r.id)
    assert result["detected_platform"] == "custom"
    assert result["recommendation"] == "needs_custom_scraper"
    assert result["dry_run"] is None
    assert result["scraping_recommended"] is False


def test_probe_shopify_with_products_recommends_enable(db, monkeypatch):
    _shoe = Shoe(brand="Nike", model="Pegasus", msrp=180.0, is_active=True)
    db.add(_shoe)
    r = _retailer(db, name="New Shopify", platform="custom")
    monkeypatch.setattr(onboarding, "determine_platform", lambda **kw: ("shopify", True))
    fake = _FakeScraper(products=[{
        "price": 129.99,
        "sizes_available": ["9", "10"],
        "product_url": "https://x/p/pegasus",
    }])
    monkeypatch.setattr(onboarding, "build_dynamic_scraper", lambda retailer: fake)
    result = onboarding.probe_retailer(db, r.id)
    assert result["detected_platform"] == "shopify"
    assert result["recommendation"] == "enable_scraping"
    assert result["dry_run"]["status"] == "success"
    assert result["dry_run"]["products_found"] == 1
    assert result["dry_run"]["sample_price"] == 129.99
    assert result["sample_shoe"] == "Nike Pegasus"


def test_probe_shopify_no_products_reports_not_found(db, monkeypatch):
    r = _retailer(db, name="Empty Shopify", platform="custom")
    monkeypatch.setattr(onboarding, "determine_platform", lambda **kw: ("shopify", True))
    monkeypatch.setattr(onboarding, "build_dynamic_scraper", lambda retailer: _FakeScraper(products=[]))
    result = onboarding.probe_retailer(db, r.id, sample_brand="Hoka", sample_model="Clifton")
    assert result["dry_run"]["status"] == "not_found"
    assert result["sample_shoe"] == "Hoka Clifton"


def test_probe_does_not_persist_platform(db, monkeypatch):
    r = _retailer(db, name="Untouched", platform="custom")
    monkeypatch.setattr(onboarding, "determine_platform", lambda **kw: ("shopify", True))
    monkeypatch.setattr(onboarding, "build_dynamic_scraper", lambda retailer: _FakeScraper(products=[]))
    onboarding.probe_retailer(db, r.id)
    db.refresh(r)
    assert r.platform == "custom"  # probe never writes
    assert r.scraping_enabled is False


# --------------------------------------------------------------------------
# apply_onboarding
# --------------------------------------------------------------------------

def test_apply_onboarding_shopify_enables_scraping(db):
    r = _retailer(db, name="To Enable", platform="custom")
    onboarding.apply_onboarding(db, r.id, platform="shopify")
    db.refresh(r)
    assert r.platform == "shopify"
    assert r.scraping_enabled is True
    assert r.scraper_config is None
    # And it leaves the queue.
    assert onboarding.retailers_needing_onboarding(db) == []


def test_apply_onboarding_algolia_stores_config(db):
    r = _retailer(db, name="Algolia To Enable", platform="custom")
    onboarding.apply_onboarding(db, r.id, platform="algolia", scraper_config=_ALGOLIA_CREDS)
    db.refresh(r)
    assert r.platform == "algolia"
    assert r.scraper_config == _ALGOLIA_CREDS
    assert r.scraping_enabled is True


def test_apply_onboarding_algolia_without_creds_raises(db):
    r = _retailer(db, name="Bad Algolia", platform="custom")
    with pytest.raises(ValueError):
        onboarding.apply_onboarding(db, r.id, platform="algolia", scraper_config={"algolia_app_id": "APP"})


def test_apply_onboarding_custom_platform_raises(db):
    r = _retailer(db, name="Nope", platform="custom")
    with pytest.raises(ValueError):
        onboarding.apply_onboarding(db, r.id, platform="custom")


def test_apply_onboarding_missing_retailer_raises(db):
    with pytest.raises(LookupError):
        onboarding.apply_onboarding(db, 9999, platform="shopify")


# --------------------------------------------------------------------------
# mark_unscrapable
# --------------------------------------------------------------------------

def test_mark_unscrapable_records_and_leaves_queue(db):
    r = _retailer(db, name="Give Up", platform="custom")
    onboarding.mark_unscrapable(db, r.id, reason="Cloudflare challenge")
    db.refresh(r)
    assert r.scraper_config["unscrapable"] is True
    assert r.scraper_config["unscrapable_reason"] == "Cloudflare challenge"
    assert r.scraping_enabled is False
    assert onboarding.retailers_needing_onboarding(db) == []


def test_mark_unscrapable_blank_reason_raises(db):
    r = _retailer(db, name="No Reason", platform="custom")
    with pytest.raises(ValueError):
        onboarding.mark_unscrapable(db, r.id, reason="   ")


def test_mark_unscrapable_missing_retailer_raises(db):
    with pytest.raises(LookupError):
        onboarding.mark_unscrapable(db, 9999, reason="gone")


# --------------------------------------------------------------------------
# scrape_health integration
# --------------------------------------------------------------------------

def test_scrape_health_surfaces_needs_onboarding(db):
    _retailer(db, name="Fresh Store", platform="custom")
    _retailer(db, name="Working Shopify", platform="shopify")
    health = scrape_history.scrape_health(db)
    assert [r["name"] for r in health["needs_onboarding"]] == ["Fresh Store"]
