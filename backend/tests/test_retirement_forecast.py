"""
Tests for the R6.2 usage forecast and radar window on rotation.retirement_pipeline.

Boundaries pinned: idle (no recent use → no date), overdue (no date), no limit
(excluded), the 6-week usage window edge, and the 8-week lookahead edge. Runs are
attributed directly (ledger arithmetic is INV-1's tests, not these).
"""
from datetime import date, datetime, timedelta

from app.models.models import Activity, Deal, OwnedShoe, Retailer, Shoe, ShoeRun
from app.services import rotation
from app.services.deal_alerts import deal_alerts

TODAY = date(2026, 10, 8)


def _owned(db, model, *, mileage, limit=800.0, shoe_type=None):
    s = OwnedShoe(brand="Asics", model=model, shoe_type=shoe_type,
                  current_mileage=mileage, mileage_limit=limit, status="active")
    db.add(s)
    db.flush()
    return s


def _run(db, shoe, km, days_ago):
    a = Activity(source="manual", activity_type="Run", distance_km=km,
                 run_date=TODAY - timedelta(days=days_ago))
    db.add(a)
    db.flush()
    db.add(ShoeRun(owned_shoe_id=shoe.id, activity_id=a.id))
    db.flush()


def _entry(db, shoe):
    return next((e for e in rotation.retirement_pipeline(db, today=TODAY) if e.shoe.id == shoe.id), None)


def test_below_threshold_with_heavy_block_appears_with_a_date(db):
    shoe = _owned(db, "Heavy", mileage=560)            # 70%
    for d in (1, 8, 15, 22, 29, 36):                   # 60 km/week → 240 left = 4 weeks
        _run(db, shoe, 60, d)
    db.commit()
    e = _entry(db, shoe)
    assert e is not None and e.pct < rotation.RETIREMENT_THRESHOLD
    assert e.forecast_status == "on_track"
    assert e.weekly_km == 60.0
    assert e.weeks_to_limit == 4.0
    assert e.projected_limit_date == (TODAY + timedelta(days=28)).isoformat()


def test_below_threshold_idle_shoe_stays_out(db):
    shoe = _owned(db, "Idle", mileage=560)
    db.commit()
    assert _entry(db, shoe) is None


def test_idle_shoe_over_threshold_has_status_but_no_date(db):
    shoe = _owned(db, "IdleHigh", mileage=620)         # 77.5%, no recent runs
    db.commit()
    e = _entry(db, shoe)
    assert e.forecast_status == "idle"
    assert e.weeks_to_limit is None and e.projected_limit_date is None


def test_overdue_has_no_date(db):
    shoe = _owned(db, "Over", mileage=810)
    _run(db, shoe, 50, 3)
    db.commit()
    e = _entry(db, shoe)
    assert e.forecast_status == "overdue"
    assert e.projected_limit_date is None


def test_no_limit_shoe_excluded(db):
    shoe = _owned(db, "NoLimit", mileage=900, limit=None)
    _run(db, shoe, 50, 3)
    db.commit()
    assert _entry(db, shoe) is None


def test_lookahead_edge_exactly_eight_weeks_is_in(db):
    shoe = _owned(db, "Edge8", mileage=480)            # 320 left
    _run(db, shoe, 240, 3)                             # 240/6 = 40 km/wk → exactly 8.0 weeks
    db.commit()
    assert _entry(db, shoe).weeks_to_limit == 8.0


def test_just_past_lookahead_is_out(db):
    shoe = _owned(db, "Edge9", mileage=480)
    _run(db, shoe, 234, 3)                             # 39 km/wk → 8.2 weeks
    db.commit()
    assert _entry(db, shoe) is None


def test_runs_older_than_six_weeks_do_not_count(db):
    shoe = _owned(db, "Old", mileage=560)
    _run(db, shoe, 500, 7 * 6)                         # exactly 6 weeks ago = outside (> since)
    db.commit()
    assert rotation.recent_weekly_km(db, today=TODAY) == {}
    assert _entry(db, shoe) is None


def test_digest_replacement_alerts_sorted_by_projected_date(db):
    r = Retailer(name="R", base_url="https://r.example")
    tracked = Shoe(brand="Nike", model="Pegasus", shoe_type="daily_trainer", msrp=200.0)
    db.add_all([r, tracked])
    db.flush()
    db.add(Deal(shoe_id=tracked.id, retailer_id=r.id, current_price=150.0, target_price=0,
                savings_amount=50.0, savings_percent=25.0, product_url="u",
                is_active=True, detected_at=datetime.utcnow()))
    far = _owned(db, "Far", mileage=700, shoe_type="daily_trainer")       # 100 left @ 10/wk = 10 wk
    near = _owned(db, "Near", mileage=700, shoe_type="daily_trainer")     # 100 left @ 50/wk = 2 wk
    idle = _owned(db, "IdleOne", mileage=700, shoe_type="daily_trainer")
    _run(db, far, 60, 3)
    _run(db, near, 300, 3)
    db.commit()
    # deal_alerts uses date.today() internally for the forecast window; pin runs to it.
    for sr in db.query(Activity).all():
        sr.run_date = date.today() - timedelta(days=3)
    db.commit()
    digest = deal_alerts(db, since=datetime.utcnow() - timedelta(days=1))
    assert [a.model for a in digest.replacement_alerts] == ["Near", "Far", "IdleOne"]
    assert digest.replacement_alerts[0].projected_limit_date is not None
    assert digest.replacement_alerts[2].projected_limit_date is None
