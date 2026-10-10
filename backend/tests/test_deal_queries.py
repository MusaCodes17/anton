"""
Deal list queries must not lazy-load per row (tech-debt §7 P2).

``DealResponse.retailer`` is a ``DealRetailerBrief`` whose ``active_promo_codes``
reads ``Retailer.promo_codes``; without eager-loading that is one SELECT per
deal row. These tests pin a constant statement count and the brief's shape.
"""
from sqlalchemy import event

from app.models.models import Deal, PromoCode, Retailer, Shoe
from app.models.schemas.deals import DealRetailerBrief, DealResponse
from app.routers import deals as deals_router
from app.services import deals as deals_svc


def _seed(db, n_deals=6, n_retailers=6):
    # One deal per retailer: lazy loads are per Retailer instance (identity map),
    # so the N+1 only shows when retailers outnumber the statement budget.
    retailers = []
    for i in range(n_retailers):
        r = Retailer(name=f"Retailer {i}", base_url=f"https://r{i}.example.com")
        db.add(r)
        db.flush()
        db.add(PromoCode(retailer_id=r.id, code=f"LIVE{i}", is_active=True))
        db.add(PromoCode(retailer_id=r.id, code=f"DEAD{i}", is_active=False))
        retailers.append(r)
    shoe = Shoe(brand="Nike", model="Vaporfly", msrp=300.0)
    db.add(shoe)
    db.flush()
    for i in range(n_deals):
        db.add(Deal(
            shoe_id=shoe.id, retailer_id=retailers[i % n_retailers].id,
            current_price=200.0 + i, savings_amount=100.0 - i,
            savings_percent=30.0 - i, product_url=f"https://x.example.com/{i}",
            is_active=True,
        ))
    db.commit()
    db.expire_all()  # force the queries under test to hit the DB


def _count_statements(db, fn):
    engine = db.get_bind()
    stmts = []

    def hook(conn, cursor, statement, *a):
        stmts.append(statement)

    event.listen(engine, "before_cursor_execute", hook)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", hook)
    return result, len(stmts)


def test_retailer_field_is_the_brief():
    assert "DealRetailerBrief" in str(DealResponse.model_fields["retailer"].annotation)


def test_list_and_serialize_statement_count_is_constant(db):
    _seed(db)

    def run():
        deals = deals_svc.list_deals(db)
        return [DealResponse.model_validate(d).model_dump() for d in deals]

    dumped, n = _count_statements(db, run)
    assert len(dumped) == 6
    # deals+shoe+retailer join, promo_codes selectin, settings (size pref) = few;
    # the point is it is not 6+ promo lookups.
    print("statements:", n)
    assert n <= 4, f"{n} statements — per-row lazy load is back"

    for d in dumped:
        assert set(d["retailer"]) == {"id", "name", "active_promo_codes"}
        codes = [c["code"] for c in d["retailer"]["active_promo_codes"]]
        assert len(codes) == 1 and codes[0].startswith("LIVE")


def test_router_returns_same_brief(db):
    _seed(db)
    deals = deals_router.get_deals(
        skip=0, limit=500, is_active=True, min_savings_percent=None, brand=None, db=db
    )
    d = DealResponse.model_validate(deals[0]).model_dump()
    brief = DealRetailerBrief.model_validate(deals[0].retailer).model_dump()
    assert d["retailer"] == brief
    assert [c["code"] for c in brief["active_promo_codes"]] == [
        f"LIVE{deals[0].retailer.name[-1]}"
    ]
