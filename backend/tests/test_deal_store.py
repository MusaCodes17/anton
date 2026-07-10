"""
Tests for the DealStore rules the deal domain leans on, beyond the MSRP money
math already pinned in test_deals.py:

- deal retirement (deactivate_deal) and requalification round-trips (INV-6);
- the orphan-retirement non-empty guard (design_decisions B10 — a transient
  empty response must never mass-extinguish deals);
- promo-code manual-beats-scraped protection (design_decisions D6).

These are the "rules, not plumbing" gaps refactor.md H1 called out.
"""
from app.models.models import Deal, PromoCode, Retailer, Shoe
from app.scrapers.deal_store import DealStore


def _retailer(db, name="TLH"):
    r = Retailer(name=name, base_url=f"https://{name}.example")
    db.add(r)
    db.flush()
    return r


def _shoe(db, *, msrp=200.0, target_price=None):
    s = Shoe(brand="Nike", model="Vaporfly", msrp=msrp, target_price=target_price)
    db.add(s)
    db.flush()
    return s


def _make_deal(db, store, shoe, retailer, *, price=160.0, url="u1"):
    created = store.upsert_deal(
        shoe=shoe, retailer=retailer, price=price, product_url=url, in_stock=True
    )
    assert created is True
    return db.query(Deal).filter(Deal.product_url == url, Deal.is_active == True).one()


# --- retirement & requalification (INV-6) ----------------------------------

def test_deactivate_deal_retires_active_deal(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()
    store = DealStore(db)
    _make_deal(db, store, shoe, r)

    assert store.deactivate_deal(shoe, r, "u1") is True
    assert db.query(Deal).one().is_active is False


def test_deactivate_deal_is_noop_when_no_active_deal(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()

    # Nothing to retire — a silent False, not an error (CLAUDE.md §7).
    assert DealStore(db).deactivate_deal(shoe, r, "u1") is False


def test_requalification_creates_a_fresh_deal_after_deactivation(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()
    store = DealStore(db)

    _make_deal(db, store, shoe, r)          # price fell below MSRP
    store.deactivate_deal(shoe, r, "u1")    # price rose back to/above MSRP

    # Price drops below MSRP again: because upsert only ever refreshes an
    # ACTIVE deal, requalification is a brand-new active row — the retired one
    # stays retired (its detected_at honesty is preserved).
    created = store.upsert_deal(
        shoe=shoe, retailer=r, price=155.0, product_url="u1", in_stock=True
    )
    assert created is True

    active = db.query(Deal).filter(Deal.is_active == True).all()
    assert len(active) == 1
    assert active[0].current_price == 155.0
    assert db.query(Deal).count() == 2  # one retired, one fresh


# --- orphan-retirement non-empty guard (B10) -------------------------------

def test_orphan_guard_ignores_empty_seen_urls(db):
    """A scrape that returned nothing (empty seen_urls) must retire nothing —
    the interlock against a transient failure wiping the whole feed (B10)."""
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()
    store = DealStore(db)
    _make_deal(db, store, shoe, r)

    assert store.deactivate_orphaned_deals(shoe, r, set()) == 0
    assert db.query(Deal).one().is_active is True


def test_orphan_retires_deal_whose_url_was_not_seen(db):
    """A real search that came back with different URLs (e.g. the shoe was
    renamed) retires the deal on the URL that no longer resolves."""
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()
    store = DealStore(db)
    _make_deal(db, store, shoe, r, url="old-url")

    retired = store.deactivate_orphaned_deals(shoe, r, {"new-url"})
    assert retired == 1
    assert db.query(Deal).one().is_active is False


def test_orphan_keeps_deal_whose_url_was_seen(db):
    r = _retailer(db)
    shoe = _shoe(db)
    db.commit()
    store = DealStore(db)
    _make_deal(db, store, shoe, r, url="u1")

    assert store.deactivate_orphaned_deals(shoe, r, {"u1"}) == 0
    assert db.query(Deal).one().is_active is True


# --- promo manual-beats-scraped (D6) ---------------------------------------

def test_new_scraped_promo_is_created(db):
    r = _retailer(db)
    db.commit()

    created = DealStore(db).upsert_promo_code(
        r, {"code": "SAVE20", "description": "20% off", "discount_percent": 20.0}
    )
    assert created is True
    promo = db.query(PromoCode).one()
    assert promo.source == "scraped"
    assert promo.discount_percent == 20.0


def test_scraped_promo_refreshes_on_reobservation(db):
    r = _retailer(db)
    db.commit()
    store = DealStore(db)
    store.upsert_promo_code(r, {"code": "SAVE20", "description": "old", "discount_percent": 20.0})

    created = store.upsert_promo_code(
        r, {"code": "SAVE20", "description": "new", "discount_percent": 25.0}
    )
    assert created is False  # same code — a refresh, not a new row
    promo = db.query(PromoCode).one()
    assert promo.description == "new"
    assert promo.discount_percent == 25.0
    assert promo.last_seen_at is not None


def test_manual_promo_is_never_overwritten_by_scraped_data(db):
    """A hand-entered code keeps its description/discount even when the scraper
    re-detects the same code with different values — manual always wins (D6).
    Only bookkeeping (last_seen_at, is_active) is touched."""
    r = _retailer(db)
    db.commit()
    manual = PromoCode(
        retailer_id=r.id,
        code="INSIDER",
        description="Members: 15% off",
        discount_percent=15.0,
        source="manual",
        is_active=False,
    )
    db.add(manual)
    db.commit()

    created = DealStore(db).upsert_promo_code(
        r, {"code": "INSIDER", "description": "SCRAPED JUNK", "discount_percent": 5.0}
    )
    assert created is False

    promo = db.query(PromoCode).one()
    assert promo.source == "manual"
    assert promo.description == "Members: 15% off"  # untouched
    assert promo.discount_percent == 15.0           # untouched
    assert promo.is_active is True                   # re-observation reactivates
    assert promo.last_seen_at is not None
