"""
Tests for MSRP-driven deal savings (DealStore.upsert_deal).

The qualification rule ("deal = price below MSRP") lives in the orchestrator
and is exercised live against scrapers; here we pin the money math that
DealStore owns: savings are measured against the shoe's MSRP, not its optional
target_price, and an MSRP edit re-computes savings on an existing deal.
"""
from app.models.models import Deal, Retailer, Shoe
from app.scrapers.deal_store import DealStore


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
