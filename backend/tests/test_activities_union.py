"""
Tests for the unified activity feed (§3 Phase-3a) and the union-aware
training stats. Exercised at the service/handler level to match the suite's
style.
"""
from datetime import date

from app.models.models import OwnedShoe, ShoeRun, StravaActivity
from app.routers.activities import get_activities
from app.services import activities as activities_svc
from app.services import strava_stats


def _strava(db, said, run_date, dist, pace_s=300, hr=150, atype="Run", moving_s=None, name="Run"):
    a = StravaActivity(
        strava_activity_id=said,
        activity_type=atype,
        name=name,
        run_date=run_date,
        distance_km=dist,
        moving_time_s=moving_s if moving_s is not None else int(pace_s * dist),
        avg_hr=hr,
        avg_pace_s_per_km=pace_s,
        elevation_gain_m=10.0,
    )
    db.add(a)
    db.flush()
    return a


def _owned(db, brand="Nike", model="Vaporfly"):
    s = OwnedShoe(brand=brand, model=model, nickname="racer", current_mileage=0)
    db.add(s)
    db.flush()
    return s


def _run(db, shoe_id, run_date, dist, source="manual", said=None, pace="5:00/km", hr=140):
    r = ShoeRun(
        owned_shoe_id=shoe_id,
        distance_km=dist,
        run_date=run_date,
        source=source,
        strava_activity_id=said,
        avg_pace=pace,
        avg_hr=hr,
    )
    db.add(r)
    db.flush()
    return r


def test_non_runs_excluded_and_sorted_desc(db):
    _strava(db, 1, date(2026, 6, 1), 10.0)
    _strava(db, 2, date(2026, 6, 20), 5.0)
    _strava(db, 3, date(2026, 6, 10), 30.0, atype="Ride")  # excluded
    db.commit()

    items = activities_svc.unified_activities(db)
    assert [a.strava_activity_id for a in items] == [2, 1]  # newest first, ride dropped
    assert all(a.source == "strava" for a in items)


def test_linked_run_appears_once_with_shoe_attribution(db):
    shoe = _owned(db)
    _strava(db, 100, date(2026, 6, 15), 10.0)
    # a shoe_run linked to that same Strava activity — must NOT double-count
    _run(db, shoe.id, date(2026, 6, 15), 10.0, source="strava", said=100)
    db.commit()

    items = activities_svc.unified_activities(db)
    assert len(items) == 1
    a = items[0]
    assert a.strava_activity_id == 100
    assert a.source == "strava"
    assert a.shoe is not None and a.shoe.model == "Vaporfly"
    assert a.shoe_run_id is not None


def test_post_export_run_appears(db):
    shoe = _owned(db)
    _strava(db, 1, date(2026, 6, 1), 8.0)
    # a COROS run logged AFTER the export, not linked to any Strava activity
    _run(db, shoe.id, date(2026, 7, 2), 12.0, source="coros")
    db.commit()

    items = activities_svc.unified_activities(db)
    assert len(items) == 2
    newest = items[0]
    assert newest.date == date(2026, 7, 2)
    assert newest.source == "coros"
    assert newest.shoe.id == shoe.id


def test_filters_year_month_shoe_min_distance_and_pagination(db):
    shoe = _owned(db)
    _strava(db, 1, date(2025, 12, 1), 5.0)
    _strava(db, 2, date(2026, 6, 5), 3.0)
    _strava(db, 3, date(2026, 6, 25), 20.0)
    _run(db, shoe.id, date(2026, 6, 15), 15.0, source="manual")
    db.commit()

    y2026 = activities_svc.unified_activities(db, year=2026)
    assert len(y2026) == 3  # strava 2 & 3 + the unlinked run; strava 1 is 2025
    assert {2, 3} <= {a.strava_activity_id for a in y2026 if a.strava_activity_id}
    assert len(activities_svc.unified_activities(db, month=6)) == 3  # two strava + one run
    assert all(a.shoe and a.shoe.id == shoe.id
               for a in activities_svc.unified_activities(db, shoe_id=shoe.id))
    assert all(a.distance_km >= 10 for a in activities_svc.unified_activities(db, min_distance_km=10))
    # pagination
    page1 = activities_svc.unified_activities(db, limit=2, offset=0)
    page2 = activities_svc.unified_activities(db, limit=2, offset=2)
    assert len(page1) == 2 and len(page2) == 2
    assert not ({id(x) for x in page1} & {id(x) for x in page2})


def test_summary_includes_both_stores(db):
    shoe = _owned(db)
    _strava(db, 1, date(2026, 6, 1), 10.0)
    _run(db, shoe.id, date(2026, 6, 20), 5.0, source="coros")  # same month, live store
    db.commit()

    monthly = strava_stats.training_summary(db, "monthly")
    jun = next(b for b in monthly if b.period == "2026-06")
    assert jun.run_count == 2
    assert jun.total_km == 15.0


def test_records_attribute_shoe_when_linked(db):
    shoe = _owned(db)
    # A fast 10k linked to a shoe, and a slower unlinked 10k.
    _strava(db, 1, date(2026, 6, 1), 10.0, pace_s=240)
    _run(db, shoe.id, date(2026, 6, 1), 10.0, source="strava", said=1)
    _strava(db, 2, date(2026, 5, 1), 10.0, pace_s=300)
    db.commit()

    # smoke: router adapter returns without error (explicit args since we bypass
    # FastAPI's Query default resolution by calling it directly)
    resp = get_activities(year=None, month=None, shoe_id=None,
                          min_distance_km=None, limit=20, offset=0, db=db)
    assert len(resp) >= 2

    bests = strava_stats.personal_bests(db)
    ten = next(b for b in bests if b.band == "10k")
    assert ten.avg_pace == "4:00/km"          # the faster one won
    assert ten.total_time_s == 2400           # 10km * 240s/km — the headline figure
    assert ten.shoe is not None and ten.shoe["id"] == shoe.id
