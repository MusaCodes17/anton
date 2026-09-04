"""
Tests for MSRP-driven deal savings (DealStore.upsert_deal).

The qualification rule ("deal = price below MSRP") lives in the orchestrator
and is exercised live against scrapers; here we pin the money math that
DealStore owns: savings are measured against the shoe's MSRP, not its optional
target_price, and an MSRP edit re-computes savings on an existing deal.
"""
from app.models.models import Deal, Retailer, Shoe
from app.scrapers.deal_store import DealStore
from app.services import deals as deals_svc


def _retailer(db, name="TLH"):
    r = Retailer(name=name, base_url=f"https://{name}.example")
    db.add(r)
    db.flush()
    return r


def _shoe(db, *, msrp, target_price=None):
    s = Shoe(brand="Nike", model="Vaporfly", msrp=msrp, target_price=target_price)
    db.add(s)
    db.flush()
    return s


def test_savings_measured_against_msrp(db):
    r = _retailer(db)
    # target_price is deliberately different from MSRP to prove it's ignored.
    shoe = _shoe(db, msrp=200.0, target_price=150.0)
    db.commit()

    created = DealStore(db).upsert_deal(
        shoe=shoe, retailer=r, price=160.0, product_url="u1", in_stock=True
    )
    assert created is True

    deal = db.query(Deal).one()
    assert deal.savings_amount == 40.0           # 200 - 160, not 150 - 160
    assert round(deal.savings_percent, 1) == 20.0  # 40/200
    assert deal.target_price == 150.0            # stored as reference only


def test_msrp_edit_refreshes_savings_on_existing_deal(db):
    r = _retailer(db)
    shoe = _shoe(db, msrp=200.0)
    db.commit()
    store = DealStore(db)

    store.upsert_deal(shoe=shoe, retailer=r, price=160.0, product_url="u1", in_stock=True)

    # MSRP corrected upward; same scraped price should deepen the discount.
    shoe.msrp = 250.0
    db.commit()
    created = store.upsert_deal(
        shoe=shoe, retailer=r, price=160.0, product_url="u1", in_stock=True
    )
    assert created is False  # not a net-new deal

    deal = db.query(Deal).one()
    assert deal.savings_amount == 90.0            # 250 - 160
    assert round(deal.savings_percent, 1) == 36.0  # 90/250


def test_no_msrp_means_no_deal(db):
    r = _retailer(db)
    shoe = _shoe(db, msrp=None, target_price=150.0)
    db.commit()

    created = DealStore(db).upsert_deal(
        shoe=shoe, retailer=r, price=140.0, product_url="u1", in_stock=True
    )
    assert created is False
    assert db.query(Deal).count() == 0


def test_list_deals_returns_more_than_legacy_100_cap(db):
    """The default limit was raised from 100 to 500 (#5): the Deals page renders
    the full active set in one round trip. With >100 active deals the endpoint
    must return them all (up to the cap), and the on-sale shoe count must equal
    DISTINCT shoe_id over active deals — not silently truncate to 100."""
    r = _retailer(db)
    # 150 active deals spread across 30 distinct shoes (5 retailers-worth of
    # variants per shoe, all on the same retailer for test simplicity).
    n_shoes, per_shoe = 30, 5
    for si in range(n_shoes):
        shoe = _shoe(db, msrp=200.0)
        for vi in range(per_shoe):
            db.add(Deal(
                shoe_id=shoe.id, retailer_id=r.id, current_price=150.0,
                savings_amount=50.0, savings_percent=25.0 + vi,  # vary ordering
                is_active=True, product_url=f"u{si}-{vi}",
            ))
    db.commit()
    total = n_shoes * per_shoe  # 150

    deals = deals_svc.list_deals(db, is_active=True)
    assert len(deals) == total                      # nothing truncated at 100
    assert len({d.shoe_id for d in deals}) == n_shoes  # on-sale shoe count intact
