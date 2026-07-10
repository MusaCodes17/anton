"""
Tests for R4.4 coupon_hunter service — stacking-opportunity logic.

Rules verified:
- A retailer with active promo codes but no active deals is in all_retailers,
  NOT in stackable.
- A retailer with both codes AND active deals is in stackable.
- Inactive promo codes and inactive deals are excluded.
- Counts and summary fields are consistent.
- Deal entries include the shoe name.
"""
from app.models.models import Deal, OwnedShoe, PromoCode, Retailer, Shoe
from app.services import coupon_hunter


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


def _promo(db, retailer, *, code="SAVE20", discount_percent=20.0, is_active=True):
    from datetime import datetime, timezone
    pc = PromoCode(
        retailer_id=retailer.id,
        code=code,
        description=f"{discount_percent}% off",
        discount_percent=discount_percent,
        source="scraped",
        is_active=is_active,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(pc)
    db.flush()
    return pc


def _deal(db, shoe, retailer, *, price=200.0, is_active=True):
    d = Deal(
        shoe_id=shoe.id,
        retailer_id=retailer.id,
        current_price=price,
        savings_amount=shoe.msrp - price,
        savings_percent=((shoe.msrp - price) / shoe.msrp) * 100,
        product_url=f"https://{retailer.name}.example/p/{shoe.model.lower()}",
        in_stock=True,
        is_active=is_active,
    )
    db.add(d)
    db.flush()
    return d


# --- empty state ---

def test_empty_when_no_promo_codes(db):
    r = _retailer(db)
    db.commit()
    result = coupon_hunter.get_stacking_opportunities(db)
    assert result["all_retailers"] == []
    assert result["stackable"] == []
    assert result["total_active_codes"] == 0
    assert result["stackable_count"] == 0


# --- promo code present but no deals ---

def test_code_without_deal_not_stackable(db):
    r = _retailer(db)
    _promo(db, r)
    db.commit()

    result = coupon_hunter.get_stacking_opportunities(db)
    assert len(result["all_retailers"]) == 1
    assert result["stackable"] == []
    assert result["stackable_count"] == 0
    assert result["total_active_codes"] == 1


# --- stackable: code + deal at same retailer ---

def test_stackable_when_code_and_deal_coexist(db):
    r = _retailer(db)
    shoe = _shoe(db)
    _promo(db, r)
    _deal(db, shoe, r)
    db.commit()

    result = coupon_hunter.get_stacking_opportunities(db)
    assert result["stackable_count"] == 1
    entry = result["stackable"][0]
    assert entry["name"] == "TLH"
    assert len(entry["promo_codes"]) == 1
    assert entry["promo_codes"][0]["code"] == "SAVE20"
    assert len(entry["deals"]) == 1


# --- inactive codes are excluded ---

def test_inactive_promo_code_excluded(db):
    r = _retailer(db)
    _promo(db, r, is_active=False)
    db.commit()

    result = coupon_hunter.get_stacking_opportunities(db)
    assert result["all_retailers"] == []
    assert result["total_active_codes"] == 0


# --- inactive deals don't make a retailer stackable ---

def test_inactive_deal_not_stackable(db):
    r = _retailer(db)
    shoe = _shoe(db)
    _promo(db, r)
    _deal(db, shoe, r, is_active=False)
    db.commit()

    result = coupon_hunter.get_stacking_opportunities(db)
    assert result["all_retailers"][0]["deals"] == []
    assert result["stackable"] == []


# --- multiple retailers, only one is stackable ---

def test_only_stackable_subset_returned(db):
    r1 = _retailer(db, name="R1")
    r2 = _retailer(db, name="R2")
    shoe = _shoe(db)
    _promo(db, r1, code="CODE1")
    _promo(db, r2, code="CODE2")
    _deal(db, shoe, r2)  # only r2 has a deal
    db.commit()

    result = coupon_hunter.get_stacking_opportunities(db)
    assert len(result["all_retailers"]) == 2
    assert len(result["stackable"]) == 1
    assert result["stackable"][0]["name"] == "R2"
    assert result["total_active_codes"] == 2


# --- deal entry includes shoe name ---

def test_deal_entry_includes_shoe_name(db):
    r = _retailer(db)
    shoe = _shoe(db, brand="Adidas", model="Adizero")
    _promo(db, r)
    _deal(db, shoe, r)
    db.commit()

    result = coupon_hunter.get_stacking_opportunities(db)
    deal_entry = result["stackable"][0]["deals"][0]
    assert deal_entry["shoe"] == "Adidas Adizero"
    assert deal_entry["price"] == 200.0
    assert deal_entry["savings_percent"] > 0


# --- stackable_count matches len(stackable) ---

def test_stackable_count_consistent(db):
    r1 = _retailer(db, name="R1")
    r2 = _retailer(db, name="R2")
    shoe = _shoe(db)
    _promo(db, r1, code="A")
    _promo(db, r2, code="B")
    _deal(db, shoe, r1)
    _deal(db, shoe, r2)
    db.commit()

    result = coupon_hunter.get_stacking_opportunities(db)
    assert result["stackable_count"] == len(result["stackable"])
    assert result["stackable_count"] == 2
