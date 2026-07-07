"""
Tests for GET /owned-shoes/{id}/replacement-deals — the deal *list* backing the
Replacement Deals card on the shoe detail page (R1.3). The count variant is
covered in test_rotation_overview.py; this pins the projection the card renders:
same-type active in-stock deals, worst-discount-first, same model excluded,
and the size-availability field the card shows.

Called at the function level, matching the suite convention (no TestClient).
"""
from app.models.models import Deal, OwnedShoe, Retailer, Shoe
from app.routers.owned_shoes import get_replacement_deals


def _owned(db, *, model="Worn Tempo", shoe_type="tempo"):
    s = OwnedShoe(brand="Adidas", model=model, shoe_type=shoe_type,
                  current_mileage=700, mileage_limit=800, status="active")
    db.add(s)
    db.flush()
    return s


def _tracked(db, *, brand="Nike", model, shoe_type):
    s = Shoe(brand=brand, model=model, shoe_type=shoe_type, msrp=200.0)
    db.add(s)
    db.flush()
    return s


def _deal(db, shoe, retailer, *, price=150.0, savings_pct=25.0,
          is_active=True, in_stock=True, sizes=None):
    d = Deal(
        shoe_id=shoe.id, retailer_id=retailer.id, current_price=price,
        savings_amount=200.0 - price, savings_percent=savings_pct,
        product_url="https://example.com/p", is_active=is_active,
        in_stock=in_stock, sizes_available=sizes,
    )
    db.add(d)
    db.flush()
    return d


def _retailer(db):
    r = Retailer(name="The Last Hunt", base_url="https://example.com")
    db.add(r)
    db.flush()
    return r


def test_lists_same_type_deals_worst_first_with_sizes(db):
    owned = _owned(db, model="Adios Pro 4", shoe_type="tempo")
    retailer = _retailer(db)
    _deal(db, _tracked(db, model="Tempo Small", shoe_type="tempo"), retailer,
          savings_pct=10.0, sizes=["9", "9.5"])
    _deal(db, _tracked(db, model="Tempo Big", shoe_type="tempo"), retailer,
          savings_pct=40.0, sizes=["10", "11"])
    db.commit()

    result = get_replacement_deals(owned.id, db)

    assert result["shoe_type"] == "tempo"
    assert result["total"] == 2
    # worst-discount-first ordering
    assert [d["model"] for d in result["deals"]] == ["Tempo Big", "Tempo Small"]
    # the size field the card renders is present and passed through verbatim
    assert result["deals"][0]["sizes_available"] == ["10", "11"]


def test_excludes_same_model_other_types_inactive_and_out_of_stock(db):
    owned = _owned(db, model="Adios Pro 4", shoe_type="tempo")
    retailer = _retailer(db)
    # same model as the owned shoe — never suggest another copy
    _deal(db, _tracked(db, model="Adios Pro 4", shoe_type="tempo"), retailer)
    # different type
    _deal(db, _tracked(db, model="Trainer", shoe_type="daily_trainer"), retailer)
    # inactive
    _deal(db, _tracked(db, model="Gone", shoe_type="tempo"), retailer, is_active=False)
    # out of stock
    _deal(db, _tracked(db, model="Sold Out", shoe_type="tempo"), retailer, in_stock=False)
    # the one that should survive
    _deal(db, _tracked(db, model="Keeper", shoe_type="tempo"), retailer, sizes=["8"])
    db.commit()

    result = get_replacement_deals(owned.id, db)

    assert [d["model"] for d in result["deals"]] == ["Keeper"]


def test_untyped_owned_shoe_returns_empty_with_message(db):
    owned = _owned(db, model="Typeless", shoe_type=None)
    db.commit()

    result = get_replacement_deals(owned.id, db)

    assert result["shoe_type"] is None
    assert result["deals"] == []
    assert result["message"]
