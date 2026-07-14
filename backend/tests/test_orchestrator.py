"""
Tests for ScrapeOrchestrator.scrape_retailer_for_shoe — the deal-qualification
truth table and orphan retirement, exercised through an injected stub scraper
(the orchestrator takes a registry injection, so no network or DOM fixtures).

Qualification rule under test (B9-v2 + D8): a deal is any price strictly below
the shoe's CURRENT MSRP AND with at least one size in stock; at/above MSRP or
out-of-stock retires any stale deal; a shoe without MSRP can never produce a deal.

H2/B10 (D2) was fixed in commit bcdddc2: orphan retirement now runs against the
union of searched + fetched URLs, so a failed detail fetch on a still-listed
product no longer orphans its live deal.
"""
from app.models.models import Deal, Retailer, Shoe
from app.scrapers.orchestrator import ScrapeOrchestrator


class StubScraper:
    """Returns canned search + detail results; `details[url] is None` simulates
    a failed detail fetch (the routine slow-page timeout in H2)."""

    def __init__(self, products, details):
        self.products = products      # list of {'product_url': ...}
        self.details = details        # url -> detail dict, or None

    def search_products_filtered(self, brand, model):
        return list(self.products)

    def get_product_details(self, url):
        return self.details.get(url)


def _detail(url, price, *, in_stock=True):
    return {
        "product_url": url,
        "price": price,
        "original_price": None,
        "in_stock": in_stock,
        "sizes_available": ["9", "10"],
        "image_url": None,
        "colorway": None,
    }


def _setup(db, *, msrp=200.0):
    retailer = Retailer(name="TLH", base_url="https://tlh.example")
    shoe = Shoe(brand="Nike", model="Vaporfly", msrp=msrp)
    db.add_all([retailer, shoe])
    db.commit()
    return retailer, shoe


def _run(db, retailer, shoe, products, details):
    orch = ScrapeOrchestrator(db, registry={retailer.name: StubScraper(products, details)})
    return orch.scrape_retailer_for_shoe(shoe, retailer)


def test_price_below_msrp_creates_a_deal(db):
    retailer, shoe = _setup(db, msrp=200.0)
    res = _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 160.0)})

    assert res["deals_found"] == 1
    deal = db.query(Deal).one()
    assert deal.is_active is True
    assert deal.savings_amount == 40.0


def test_price_at_msrp_creates_no_deal(db):
    retailer, shoe = _setup(db, msrp=200.0)
    # Boundary: strictly-below only — exactly MSRP is not a deal.
    res = _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 200.0)})

    assert res["deals_found"] == 0
    assert db.query(Deal).count() == 0


def test_no_msrp_never_produces_a_deal(db):
    retailer, shoe = _setup(db, msrp=None)
    res = _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 140.0)})

    assert res["deals_found"] == 0
    assert db.query(Deal).count() == 0


def test_price_rising_to_msrp_deactivates_existing_deal(db):
    retailer, shoe = _setup(db, msrp=200.0)
    _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 160.0)})
    assert db.query(Deal).one().is_active is True

    # Next scrape: same URL, price recovered to MSRP — the stale deal retires.
    _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 205.0)})
    assert db.query(Deal).one().is_active is False


def test_deal_orphaned_when_its_url_disappears_from_search(db):
    retailer, shoe = _setup(db, msrp=200.0)
    _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 160.0)})
    assert db.query(Deal).filter(Deal.is_active == True).count() == 1

    # Shoe renamed → search now resolves a different product page (u2). The old
    # URL is never revisited, so the orphan pass retires it.
    _run(db, retailer, shoe, [{"product_url": "u2"}], {"u2": _detail("u2", 150.0)})
    active = db.query(Deal).filter(Deal.is_active == True).all()
    assert len(active) == 1
    assert active[0].product_url == "u2"
    assert db.query(Deal).filter(Deal.product_url == "u1", Deal.is_active == False).count() == 1


def test_partial_detail_failure_does_not_orphan_a_live_deal(db):
    """H2/B10 fix: a product still returned by search must keep its live deal
    even when its detail fetch fails this scrape — orphan retirement runs
    against the union of searched + fetched URLs, not fetched-only."""
    retailer, shoe = _setup(db, msrp=200.0)
    # Two live deals.
    _run(
        db, retailer, shoe,
        [{"product_url": "u1"}, {"product_url": "u2"}],
        {"u1": _detail("u1", 160.0), "u2": _detail("u2", 170.0)},
    )
    assert db.query(Deal).filter(Deal.is_active == True).count() == 2

    # Next scrape: u1's detail fetch times out (None); u2 succeeds. u1 is still
    # returned by search, so its deal survives (u2 refreshes in place).
    _run(
        db, retailer, shoe,
        [{"product_url": "u1"}, {"product_url": "u2"}],
        {"u1": None, "u2": _detail("u2", 170.0)},
    )
    assert db.query(Deal).filter(Deal.product_url == "u1", Deal.is_active == True).count() == 1
    assert db.query(Deal).filter(Deal.is_active == True).count() == 2


# ── D8: out-of-stock qualification guard ─────────────────────────────────────


def test_out_of_stock_below_msrp_does_not_create_deal(db):
    """D8: a below-MSRP product with no sizes available must not become a deal."""
    retailer, shoe = _setup(db, msrp=200.0)
    res = _run(
        db, retailer, shoe,
        [{"product_url": "u1"}],
        {"u1": _detail("u1", 160.0, in_stock=False)},
    )

    assert res["deals_found"] == 0
    assert db.query(Deal).count() == 0


def test_out_of_stock_retires_existing_deal(db):
    """D8: when a previously-qualifying deal goes out of stock it must be retired."""
    retailer, shoe = _setup(db, msrp=200.0)
    # First scrape: in stock → deal created.
    _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 160.0)})
    assert db.query(Deal).one().is_active is True

    # Second scrape: same price, now out of stock → deal retired.
    _run(
        db, retailer, shoe,
        [{"product_url": "u1"}],
        {"u1": _detail("u1", 160.0, in_stock=False)},
    )
    assert db.query(Deal).one().is_active is False


def test_stock_return_requalifies_retired_deal(db):
    """D8: a deal retired for OOS must requalify when stock returns."""
    retailer, shoe = _setup(db, msrp=200.0)
    # Create → retire on OOS.
    _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 160.0)})
    _run(
        db, retailer, shoe,
        [{"product_url": "u1"}],
        {"u1": _detail("u1", 160.0, in_stock=False)},
    )
    assert db.query(Deal).filter(Deal.is_active == True).count() == 0

    # Stock returns → new active deal.
    _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 160.0)})
    active = db.query(Deal).filter(Deal.is_active == True).all()
    assert len(active) == 1
    assert active[0].current_price == 160.0


# ── INV-6 / B9-v2: qualification is against MSRP; target_price is never consulted ──


def test_price_below_target_but_above_msrp_is_not_a_deal(db):
    """INV-6: qualification compares the scraped price to MSRP, never to
    target_price. A price under a *generous* target_price but at/above MSRP must
    not create a deal — guards against reintroducing target into deal math
    (CLAUDE.md §6 trap / design_decisions B9-v2)."""
    retailer, shoe = _setup(db, msrp=200.0)
    shoe.target_price = 250.0  # optional personal 'ping me' threshold, above MSRP
    db.commit()

    res = _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 220.0)})

    assert res["deals_found"] == 0          # 220 ≥ 200 MSRP → no deal; 220 < 250 target is irrelevant
    assert db.query(Deal).count() == 0


def test_price_requalifies_after_rising_above_msrp(db):
    """The price analogue of test_stock_return_requalifies_retired_deal: a deal
    retired because its price rose to/above MSRP must requalify as a fresh active
    deal when the price falls back below MSRP, leaving the retired row retired
    (its detected_at honesty preserved)."""
    retailer, shoe = _setup(db, msrp=200.0)
    _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 160.0)})
    _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 210.0)})  # retire
    assert db.query(Deal).filter(Deal.is_active == True).count() == 0

    # Price drops below MSRP again → a brand-new active deal.
    _run(db, retailer, shoe, [{"product_url": "u1"}], {"u1": _detail("u1", 150.0)})
    active = db.query(Deal).filter(Deal.is_active == True).all()
    assert len(active) == 1
    assert active[0].current_price == 150.0
    assert active[0].savings_amount == 50.0   # 200 - 150, measured vs MSRP
    assert db.query(Deal).count() == 2         # one retired, one fresh
