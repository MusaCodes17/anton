"""
Tests for R2.5 scrape observability.

Two rules, both boundary-explicit:
  1. ScrapeOrchestrator.scrape_retailer() writes exactly one ScrapeRun per
     retailer attempt, finalized to "success"/"error" with the right counts —
     the single sanctioned write path for the scrape_runs table.
  2. services.scrape_history distills a retailer's latest run into the health
     verdict the UI/MCP show, with the "quietly broken" case (finished clean,
     found zero products) mapping to "warning" — the whole point of the feature.

The scrapers are faked (a dict registry injected into the orchestrator) so the
tests exercise real DealStore + real ScrapeRun persistence without touching a
live retailer site.
"""
from datetime import datetime, timezone

from app.models.models import Retailer, ScrapeRun, Shoe
from app.scrapers.orchestrator import ScrapeOrchestrator
from app.services import scrape_history


def _retailer(db, name="TLH"):
    r = Retailer(name=name, base_url=f"https://{name}.example")
    db.add(r)
    db.flush()
    return r


def _shoe(db, *, brand="Nike", model="Vaporfly", msrp=250.0):
    s = Shoe(brand=brand, model=model, msrp=msrp)
    db.add(s)
    db.flush()
    return s


class _SuccessScraper:
    """Finds one in-stock product below MSRP → a recorded price + a deal."""

    def __init__(self, price=200.0):
        self.price = price

    def search_products_filtered(self, brand, model):
        return [{"product_url": "https://r/p1"}]

    def get_product_details(self, url):
        return {
            "product_url": url,
            "price": self.price,
            "original_price": None,
            "in_stock": True,
            "sizes_available": ["9", "10"],
            "image_url": None,
            "colorway": None,
        }


class _EmptyScraper:
    """The 'quietly broken' case: search returns nothing, no error raised."""

    def search_products_filtered(self, brand, model):
        return []

    def get_product_details(self, url):  # pragma: no cover - never reached
        return None


class _ErrorScraper:
    """Search itself blows up — caught by scrape_retailer_for_shoe into errors."""

    def search_products_filtered(self, brand, model):
        raise RuntimeError("boom")

    def get_product_details(self, url):  # pragma: no cover - never reached
        return None


def _orchestrator(db, retailer, scraper):
    return ScrapeOrchestrator(db, registry={retailer.name: scraper})


# --------------------------------------------------------------------------
# scrape_retailer writes the run
# --------------------------------------------------------------------------

def test_success_run_records_counts_and_status(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    agg = _orchestrator(db, r, _SuccessScraper()).scrape_retailer(r, [shoe], trigger="manual")

    run = db.query(ScrapeRun).one()
    assert run.status == "success"
    assert run.trigger == "manual"
    assert run.shoes_scraped == 1
    assert run.products_found == 1
    assert run.prices_recorded == 1
    assert run.deals_found == 1          # 200 < 250 MSRP
    assert run.error is None
    assert run.finished_at is not None
    # last_scraped_at is stamped to the run's finish time.
    assert r.last_scraped_at == run.finished_at
    # Aggregate handed back to the caller mirrors the row.
    assert agg["products_found"] == 1 and agg["deals_found"] == 1


def test_empty_scrape_is_success_with_zero_products(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    _orchestrator(db, r, _EmptyScraper()).scrape_retailer(r, [shoe])

    run = db.query(ScrapeRun).one()
    assert run.status == "success"       # no error was raised...
    assert run.products_found == 0       # ...but nothing came back
    assert run.error is None


def test_error_scrape_captures_status_and_message(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    _orchestrator(db, r, _ErrorScraper()).scrape_retailer(r, [shoe])

    run = db.query(ScrapeRun).one()
    assert run.status == "error"
    assert run.error and "boom" in run.error
    assert run.products_found == 0


def test_one_run_per_retailer_attempt(db):
    r = _retailer(db)
    shoes = [_shoe(db, model="Vaporfly"), _shoe(db, model="Alphafly")]
    db.commit()

    _orchestrator(db, r, _SuccessScraper()).scrape_retailer(r, shoes)

    # Two shoes, still exactly one run row — grain is per-retailer-attempt.
    run = db.query(ScrapeRun).one()
    assert run.shoes_scraped == 2
    assert run.products_found == 2


# --------------------------------------------------------------------------
# scrape_history health derivation
# --------------------------------------------------------------------------

def test_health_ok_warning_error_unknown(db):
    ok = _retailer(db, "OK")
    warn = _retailer(db, "Warn")
    err = _retailer(db, "Err")
    _retailer(db, "Never")               # no runs → unknown
    shoe = _shoe(db)
    db.commit()

    _orchestrator(db, ok, _SuccessScraper()).scrape_retailer(ok, [shoe])
    _orchestrator(db, warn, _EmptyScraper()).scrape_retailer(warn, [shoe])
    _orchestrator(db, err, _ErrorScraper()).scrape_retailer(err, [shoe])

    health = {r["name"]: r["health"] for r in scrape_history.retailer_health(db)}
    assert health == {"OK": "ok", "Warn": "warning", "Err": "error", "Never": "unknown"}


def test_running_run_reads_as_unknown(db):
    r = _retailer(db)
    db.add(ScrapeRun(retailer_id=r.id, status="running"))
    db.commit()

    entry = next(e for e in scrape_history.retailer_health(db) if e["name"] == r.name)
    assert entry["health"] == "unknown"
    assert entry["latest_run"]["status"] == "running"


def test_latest_run_wins_and_trend_is_newest_first(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()
    orch = _orchestrator(db, r, _SuccessScraper())

    orch.scrape_retailer(r, [shoe])      # run 1
    orch.scrape_retailer(r, [shoe])      # run 2 (latest)

    entry = next(e for e in scrape_history.retailer_health(db) if e["name"] == r.name)
    ids = [run["id"] for run in entry["trend"]]
    assert ids == sorted(ids, reverse=True)          # newest first
    assert entry["latest_run"]["id"] == max(ids)


def test_recent_runs_span_all_retailers_newest_first(db):
    a = _retailer(db, "A")
    b = _retailer(db, "B")
    shoe = _shoe(db)
    db.commit()

    _orchestrator(db, a, _SuccessScraper()).scrape_retailer(a, [shoe])
    _orchestrator(db, b, _SuccessScraper()).scrape_retailer(b, [shoe])

    payload = scrape_history.scrape_health(db)
    runs = payload["recent_runs"]
    assert len(runs) == 2
    assert {run["retailer_name"] for run in runs} == {"A", "B"}
    assert runs[0]["id"] > runs[1]["id"]             # newest first


# --------------------------------------------------------------------------
# R4.2 — watchdog alert for consecutive scrape failures
# --------------------------------------------------------------------------

def test_watchdog_fires_after_n_consecutive_errors(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()
    orch = _orchestrator(db, r, _ErrorScraper())

    for _ in range(3):
        orch.scrape_retailer(r, [shoe])

    entry = next(e for e in scrape_history.retailer_health(db) if e["name"] == r.name)
    assert entry["watchdog_alert"] is True
    assert entry["watchdog_reason"] is not None


def test_watchdog_fires_on_mixed_error_and_warning(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    # Two error runs then a warning (0 products, no exception).
    _orchestrator(db, r, _ErrorScraper()).scrape_retailer(r, [shoe])
    _orchestrator(db, r, _ErrorScraper()).scrape_retailer(r, [shoe])
    _orchestrator(db, r, _EmptyScraper()).scrape_retailer(r, [shoe])

    entry = next(e for e in scrape_history.retailer_health(db) if e["name"] == r.name)
    assert entry["watchdog_alert"] is True


def test_watchdog_no_fire_when_success_in_streak(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    # Two errors then a success — streak is broken.
    _orchestrator(db, r, _ErrorScraper()).scrape_retailer(r, [shoe])
    _orchestrator(db, r, _ErrorScraper()).scrape_retailer(r, [shoe])
    _orchestrator(db, r, _SuccessScraper()).scrape_retailer(r, [shoe])

    entry = next(e for e in scrape_history.retailer_health(db) if e["name"] == r.name)
    assert entry["watchdog_alert"] is False


def test_watchdog_no_fire_below_threshold(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    # Only two bad runs — below the threshold of 3.
    for _ in range(2):
        _orchestrator(db, r, _ErrorScraper()).scrape_retailer(r, [shoe])

    entry = next(e for e in scrape_history.retailer_health(db) if e["name"] == r.name)
    assert entry["watchdog_alert"] is False


def test_watchdog_skips_running_run(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    # Three error runs, then an in-flight "running" run added directly.
    for _ in range(3):
        _orchestrator(db, r, _ErrorScraper()).scrape_retailer(r, [shoe])
    db.add(ScrapeRun(retailer_id=r.id, status="running"))
    db.commit()

    entry = next(e for e in scrape_history.retailer_health(db) if e["name"] == r.name)
    # The running run is excluded from the streak — the 3 errors still fire.
    assert entry["watchdog_alert"] is True


def test_retailers_needing_attention_in_summary(db):
    ok = _retailer(db, "OK")
    bad = _retailer(db, "Bad")
    shoe = _shoe(db)
    db.commit()

    _orchestrator(db, ok, _SuccessScraper()).scrape_retailer(ok, [shoe])
    for _ in range(3):
        _orchestrator(db, bad, _ErrorScraper()).scrape_retailer(bad, [shoe])

    payload = scrape_history.scrape_health(db)
    names = [r["name"] for r in payload["retailers_needing_attention"]]
    assert "Bad" in names
    assert "OK" not in names


# --------------------------------------------------------------------------
# shoe-sync scope — ScrapeRun per retailer, excluded from health/watchdog
# --------------------------------------------------------------------------

def test_scrape_shoe_emits_one_run_per_retailer(db):
    r1 = _retailer(db, "R1")
    r2 = _retailer(db, "R2")
    shoe = _shoe(db)
    db.commit()

    ScrapeOrchestrator(db, registry={"R1": _SuccessScraper(), "R2": _SuccessScraper()}).scrape_shoe(shoe.id)

    runs = db.query(ScrapeRun).order_by(ScrapeRun.id).all()
    assert len(runs) == 2
    assert all(r.trigger == "shoe-sync" for r in runs)
    assert all(r.shoes_scraped == 1 for r in runs)
    assert all(r.status == "success" for r in runs)
    assert all(r.products_found == 1 for r in runs)


def test_shoe_sync_zero_products_does_not_cause_warning(db):
    """A shoe not stocked at a retailer yields 0 products — must not pollute health."""
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    ScrapeOrchestrator(db, registry={r.name: _EmptyScraper()}).scrape_shoe(shoe.id)

    entry = next(e for e in scrape_history.retailer_health(db) if e["name"] == r.name)
    # No catalog runs → unknown, not warning from the shoe-sync zero-products row.
    assert entry["health"] == "unknown"


def test_shoe_sync_does_not_mask_catalog_health(db):
    """A catalog 'ok' run stays ok even if a later shoe-sync returns 0 products."""
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    ScrapeOrchestrator(db, registry={r.name: _SuccessScraper()}).scrape_retailer(r, [shoe], trigger="manual")
    ScrapeOrchestrator(db, registry={r.name: _EmptyScraper()}).scrape_shoe(shoe.id)

    entry = next(e for e in scrape_history.retailer_health(db) if e["name"] == r.name)
    assert entry["health"] == "ok"


def test_shoe_sync_runs_appear_in_recent_runs(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    ScrapeOrchestrator(db, registry={r.name: _SuccessScraper()}).scrape_shoe(shoe.id)

    payload = scrape_history.scrape_health(db)
    assert len(payload["recent_runs"]) == 1
    assert payload["recent_runs"][0]["trigger"] == "shoe-sync"


def test_shoe_sync_does_not_contribute_to_watchdog(db):
    """Three consecutive shoe-sync errors must not fire the catalog-health watchdog."""
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    for _ in range(3):
        ScrapeOrchestrator(db, registry={r.name: _ErrorScraper()}).scrape_shoe(shoe.id)

    entry = next(e for e in scrape_history.retailer_health(db) if e["name"] == r.name)
    assert entry["watchdog_alert"] is False
