"""
Tests for services/deal_alerts.py (R3.2).

Covers:
- new_deals: detected_at after/before since, inactive excluded, sorted by savings
- price_drops: drop detected, unchanged, increased, no reference, no double-count with new_deals
- replacement_alerts: pipeline + new type-deal, no new deal, below pipeline threshold, no shoe_type
- first_run: since=None defaults to 7-day window, first_run=True
- has_alerts: False when empty, True when any section non-empty

All datetimes are naive UTC to match SQLite storage behaviour.
"""
from datetime import datetime, timedelta

import pytest

from app.models.models import Deal, OwnedShoe, PriceRecord, Retailer, Shoe
from app.services.deal_alerts import FIRST_RUN_DAYS, deal_alerts

# Fixed clock: BEFORE < SINCE < AFTER < NOW
NOW   = datetime(2026, 7, 10, 12, 0, 0)
SINCE = datetime(2026, 7, 8, 0, 0, 0)    # the high-water mark we inject
AFTER = datetime(2026, 7, 9, 6, 0, 0)    # after SINCE  → "new" event
BEFORE = datetime(2026, 7, 6, 0, 0, 0)   # before SINCE → "old" event


# ── helpers ───────────────────────────────────────────────────────────────────

def _retailer(db, name="Altitude"):
    r = Retailer(name=name, base_url=f"https://{name.lower()}.example")
    db.add(r)
    db.flush()
    return r


def _tracked_shoe(db, brand="Adidas", model="Adios Pro 4", *,
                  msrp=250.0, shoe_type="long_distance_racer"):
    s = Shoe(brand=brand, model=model, msrp=msrp, shoe_type=shoe_type, is_active=True)
    db.add(s)
    db.flush()
    return s


def _deal(db, shoe, retailer, price=180.0, *, detected_at=AFTER, is_active=True):
    savings_amount = (shoe.msrp or 250.0) - price
    savings_pct = savings_amount / (shoe.msrp or 250.0) * 100
    d = Deal(
        shoe_id=shoe.id,
        retailer_id=retailer.id,
        current_price=price,
        savings_amount=savings_amount,
        savings_percent=savings_pct,
        product_url="https://example.com/deal",
        is_active=is_active,
        detected_at=detected_at,
    )
    db.add(d)
    db.flush()
    return d


def _price_rec(db, shoe, retailer, price=180.0, *, scraped_at=AFTER):
    r = PriceRecord(
        shoe_id=shoe.id,
        retailer_id=retailer.id,
        product_url="https://example.com/product",
        price=price,
        in_stock=True,
        scraped_at=scraped_at,
    )
    db.add(r)
    db.flush()
    return r


def _owned_shoe(db, brand="Asics", model="Nimbus 24", *,
                mileage=800.0, limit=1000.0, shoe_type="daily_trainer"):
    s = OwnedShoe(
        brand=brand, model=model, shoe_type=shoe_type,
        current_mileage=mileage, mileage_limit=limit, status="active",
    )
    db.add(s)
    db.flush()
    return s


# ── new_deals ─────────────────────────────────────────────────────────────────

def test_new_deal_after_since_is_reported(db):
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, detected_at=AFTER)
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert len(digest.new_deals) == 1
    assert digest.new_deals[0].brand == "Adidas"
    assert digest.new_deals[0].savings_percent > 0


def test_new_deal_before_since_excluded(db):
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, detected_at=BEFORE)
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.new_deals == []


def test_inactive_deal_not_in_new_deals(db):
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, detected_at=AFTER, is_active=False)
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.new_deals == []


def test_new_deals_sorted_by_savings_percent(db):
    r = _retailer(db)
    s1 = _tracked_shoe(db, "Nike", "Vaporfly 3", msrp=300.0)
    s2 = _tracked_shoe(db, "Adidas", "Adios Pro 4", msrp=250.0)
    _deal(db, s1, r, price=220.0, detected_at=AFTER)   # (300-220)/300 ≈ 26.7%
    _deal(db, s2, r, price=150.0, detected_at=AFTER)   # (250-150)/250 = 40%
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert len(digest.new_deals) == 2
    assert digest.new_deals[0].brand == "Adidas"   # bigger discount first


# ── price_drops ───────────────────────────────────────────────────────────────

def test_price_drop_detected(db):
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, price=180.0, detected_at=BEFORE)   # pre-existing
    _price_rec(db, s, r, price=200.0, scraped_at=BEFORE)  # reference price
    _price_rec(db, s, r, price=165.0, scraped_at=AFTER)   # lower — a drop
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert len(digest.price_drops) == 1
    drop = digest.price_drops[0]
    assert drop.old_price == 200.0
    assert drop.new_price == 165.0
    assert drop.drop_amount == pytest.approx(35.0)
    assert drop.drop_percent == pytest.approx(35 / 200 * 100)


def test_price_unchanged_no_drop(db):
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, price=180.0, detected_at=BEFORE)
    _price_rec(db, s, r, price=180.0, scraped_at=BEFORE)
    _price_rec(db, s, r, price=180.0, scraped_at=AFTER)  # same price
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.price_drops == []


def test_price_increased_no_drop(db):
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, price=185.0, detected_at=BEFORE)
    _price_rec(db, s, r, price=180.0, scraped_at=BEFORE)
    _price_rec(db, s, r, price=195.0, scraped_at=AFTER)  # higher — not a drop
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.price_drops == []


def test_no_reference_record_no_drop(db):
    """New price record exists but nothing before since → can't compare."""
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, price=180.0, detected_at=BEFORE)
    _price_rec(db, s, r, price=165.0, scraped_at=AFTER)  # no reference record
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.price_drops == []


def test_new_deal_not_double_counted_as_price_drop(db):
    """A deal detected after since → new_deals only, not price_drops."""
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, price=180.0, detected_at=AFTER)    # new deal
    _price_rec(db, s, r, price=200.0, scraped_at=BEFORE)  # old ref
    _price_rec(db, s, r, price=180.0, scraped_at=AFTER)   # new lower price
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert len(digest.new_deals) == 1
    assert digest.price_drops == []   # excluded: deal is post-since, not pre-existing


def test_multiple_new_records_collapses_to_min(db):
    """Two new price records for same deal → only the minimum triggers a drop check."""
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, price=175.0, detected_at=BEFORE)
    _price_rec(db, s, r, price=200.0, scraped_at=BEFORE)   # reference
    _price_rec(db, s, r, price=180.0, scraped_at=AFTER)    # new — minor drop
    _price_rec(db, s, r, price=165.0, scraped_at=AFTER + timedelta(hours=1))  # new — bigger drop
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert len(digest.price_drops) == 1
    assert digest.price_drops[0].new_price == 165.0   # took the minimum


def test_price_drops_sorted_by_drop_amount(db):
    r1 = _retailer(db, "Altitude")
    r2 = _retailer(db, "TLH")
    s = _tracked_shoe(db)
    _deal(db, s, r1, price=160.0, detected_at=BEFORE)
    _deal(db, s, r2, price=170.0, detected_at=BEFORE)
    _price_rec(db, s, r1, price=200.0, scraped_at=BEFORE)
    _price_rec(db, s, r2, price=200.0, scraped_at=BEFORE)
    _price_rec(db, s, r1, price=190.0, scraped_at=AFTER)   # $10 drop
    _price_rec(db, s, r2, price=160.0, scraped_at=AFTER)   # $40 drop
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert len(digest.price_drops) == 2
    assert digest.price_drops[0].drop_amount == pytest.approx(40.0)  # biggest first


# ── replacement_alerts ────────────────────────────────────────────────────────

def test_replacement_alert_for_pipeline_shoe(db):
    r = _retailer(db)
    watched = _tracked_shoe(db, "Nike", "Pegasus 41", shoe_type="daily_trainer")
    _owned_shoe(db, "Asics", "Nimbus 24", mileage=800.0, limit=1000.0, shoe_type="daily_trainer")
    _deal(db, watched, r, price=150.0, detected_at=AFTER)
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert len(digest.replacement_alerts) == 1
    alert = digest.replacement_alerts[0]
    assert alert.shoe_type == "daily_trainer"
    assert alert.pct >= 0.75
    assert len(alert.new_deals) == 1
    assert alert.new_deals[0]["brand"] == "Nike"


def test_no_replacement_alert_when_deal_predates_since(db):
    r = _retailer(db)
    watched = _tracked_shoe(db, shoe_type="daily_trainer")
    _owned_shoe(db, mileage=800.0, limit=1000.0, shoe_type="daily_trainer")
    _deal(db, watched, r, detected_at=BEFORE)   # old deal — not new
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.replacement_alerts == []


def test_no_replacement_alert_below_pipeline_threshold(db):
    """60% mileage → not in the pipeline → no alert."""
    r = _retailer(db)
    watched = _tracked_shoe(db, shoe_type="daily_trainer")
    _owned_shoe(db, mileage=600.0, limit=1000.0, shoe_type="daily_trainer")  # 60%
    _deal(db, watched, r, detected_at=AFTER)
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.replacement_alerts == []


def test_no_replacement_alert_when_owned_shoe_has_no_type(db):
    r = _retailer(db)
    watched = _tracked_shoe(db, shoe_type="daily_trainer")
    _owned_shoe(db, mileage=800.0, limit=1000.0, shoe_type=None)  # no type
    _deal(db, watched, r, detected_at=AFTER)
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.replacement_alerts == []


def test_replacement_alert_type_must_match(db):
    r = _retailer(db)
    watched = _tracked_shoe(db, shoe_type="long_distance_racer")   # different type
    _owned_shoe(db, mileage=800.0, limit=1000.0, shoe_type="daily_trainer")
    _deal(db, watched, r, detected_at=AFTER)
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.replacement_alerts == []


def test_no_replacement_alert_when_owned_shoe_has_no_limit(db):
    """No mileage_limit → can't compute pipeline % → not in pipeline."""
    r = _retailer(db)
    watched = _tracked_shoe(db, shoe_type="daily_trainer")
    _owned_shoe(db, mileage=800.0, limit=None, shoe_type="daily_trainer")
    _deal(db, watched, r, detected_at=AFTER)
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.replacement_alerts == []


# ── first_run + flags ─────────────────────────────────────────────────────────

def test_first_run_uses_7_day_default_window(db):
    """since=None → effective_since = now - 7 days; first_run=True."""
    r = _retailer(db)
    s = _tracked_shoe(db)
    within_window = NOW - timedelta(days=FIRST_RUN_DAYS - 1)   # 6 days ago — inside
    outside_window = NOW - timedelta(days=FIRST_RUN_DAYS + 1)  # 8 days ago — outside
    _deal(db, s, r, detected_at=within_window)
    _deal(db, _tracked_shoe(db, "Nike", "Vaporfly"), r, detected_at=outside_window)
    db.commit()
    digest = deal_alerts(db, since=None, _now=NOW)
    assert digest.first_run is True
    assert digest.since is None
    assert len(digest.new_deals) == 1   # only the recent one


def test_first_run_false_when_since_provided(db):
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.first_run is False
    assert digest.since == SINCE.isoformat()


def test_has_alerts_false_when_all_sections_empty(db):
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.has_alerts is False


def test_has_alerts_true_when_new_deal(db):
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, detected_at=AFTER)
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.has_alerts is True


def test_has_alerts_true_when_price_drop(db):
    r = _retailer(db)
    s = _tracked_shoe(db)
    _deal(db, s, r, price=180.0, detected_at=BEFORE)
    _price_rec(db, s, r, price=200.0, scraped_at=BEFORE)
    _price_rec(db, s, r, price=160.0, scraped_at=AFTER)
    db.commit()
    digest = deal_alerts(db, since=SINCE, _now=NOW)
    assert digest.has_alerts is True
