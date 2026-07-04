"""
Tests for GET /api/watchlist (Phase 2). Exercised at the handler level to
match the suite's service-oriented style.
"""
from datetime import datetime

from app.models.models import Deal, PriceRecord, Retailer, Shoe
from app.routers.watchlist import get_watchlist


def _retailer(db, name):
    r = Retailer(name=name, base_url=f"https://{name}.example")
    db.add(r)
    db.flush()
    return r


def _shoe(db, brand, model, target_price=180.0, msrp=220.0, is_active=True):
    s = Shoe(brand=brand, model=model, target_price=target_price, msrp=msrp, is_active=is_active)
    db.add(s)
    db.flush()
    return s


def test_empty_watchlist(db):
    assert get_watchlist(db=db) == []


def test_shoe_with_no_deal_is_included_with_best_ever(db):
    r = _retailer(db, "TLH")
    s = _shoe(db, "Nike", "Streakfly")
    db.add_all([
        PriceRecord(shoe_id=s.id, retailer_id=r.id, product_url="u1", price=200.0,
                    in_stock=True, scraped_at=datetime(2026, 5, 1)),
        PriceRecord(shoe_id=s.id, retailer_id=r.id, product_url="u2", price=170.0,
                    in_stock=True, scraped_at=datetime(2026, 6, 1)),
    ])
    db.commit()

    items = get_watchlist(db=db)
    assert len(items) == 1
    item = items[0]
    assert item.on_sale is False
    assert item.best_deal is None
    # Best-ever is the lowest price ever seen, not the most recent.
    assert item.best_ever_price == 170.0
    assert item.best_ever_at == datetime(2026, 6, 1)
    # Last-seen is the most recent record per retailer.
    assert len(item.last_seen) == 1
    assert item.last_seen[0].price == 170.0
    assert item.last_seen[0].retailer_name == "TLH"


def test_on_sale_shoe_reports_best_deal_and_sorts_first(db):
    r1 = _retailer(db, "TLH")
    r2 = _retailer(db, "Altitude")
    watched = _shoe(db, "Asics", "Metaspeed")
    onsale = _shoe(db, "Adidas", "Adios Pro")

    # onsale has two active deals at different retailers — best = lowest price.
    db.add_all([
        Deal(shoe_id=onsale.id, retailer_id=r1.id, current_price=150.0, target_price=160.0,
             savings_amount=70.0, savings_percent=31.8, product_url="d1", in_stock=True, is_active=True),
        Deal(shoe_id=onsale.id, retailer_id=r2.id, current_price=140.0, target_price=160.0,
             savings_amount=80.0, savings_percent=36.4, product_url="d2", in_stock=True, is_active=True),
        # an inactive deal must be ignored
        Deal(shoe_id=onsale.id, retailer_id=r1.id, current_price=130.0, target_price=160.0,
             savings_amount=90.0, savings_percent=40.0, product_url="d3", in_stock=True, is_active=False),
        PriceRecord(shoe_id=watched.id, retailer_id=r1.id, product_url="w1", price=210.0, in_stock=True),
    ])
    db.commit()

    items = get_watchlist(db=db)
    assert [it.model for it in items] == ["Adios Pro", "Metaspeed"]  # on-sale first
    best = items[0].best_deal
    assert items[0].on_sale is True
    assert best is not None
    assert best.current_price == 140.0  # lowest active, ignores inactive 130
    assert best.retailer_name == "Altitude"


def test_inactive_shoe_excluded(db):
    _shoe(db, "Hoka", "Rocket", is_active=False)
    db.commit()
    assert get_watchlist(db=db) == []
