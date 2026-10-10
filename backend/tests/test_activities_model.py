"""
Tests for the canonical `activities` table + attribution write paths (§3
Phase-5): log_run mints an activity + attribution, COROS dedup keys off
activities.coros_activity_id, delete_run tears down the right rows (keeping the
frozen Strava archive), and lifetime stats read through the join.
"""
from datetime import date

import pytest

from app.models.models import Activity, OwnedShoe, ShoeRun
from app.services import coros as coros_svc
from app.services import rotation


def _shoe(db, mileage=0.0):
    s = OwnedShoe(brand="Adidas", model="Adios Pro 4",
                  starting_mileage=mileage, current_mileage=mileage)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_log_run_creates_activity_and_attribution(db):
    shoe = _shoe(db)
    result = rotation.log_run(
        db, shoe.id, distance_km=10.0, run_date=date(2026, 7, 1),
        source="manual", avg_pace="5:00/km", avg_hr=150, notes="easy",
    )
    # One activity, one attribution, correctly linked.
    act = db.query(Activity).one()
    assert act.source == "manual"
    assert act.activity_type == "Run"
    assert act.distance_km == 10.0
    assert act.avg_pace_s_per_km == 300  # 5:00/km
    assert act.description == "easy"     # per-run notes land on the activity
    attr = db.query(ShoeRun).one()
    assert attr.activity_id == act.id
    assert attr.owned_shoe_id == shoe.id
    assert result.activity.id == act.id
    assert result.shoe.current_mileage == pytest.approx(10.0)
    # Run fields live on the joined activity (ShoeRun proxies retired 2026-10-10).
    assert attr.activity.distance_km == 10.0 and attr.activity.source == "manual"
    assert rotation.shoe_run_payload(attr)["avg_pace"] == "5:00/km"


def test_union_reads_one_row_per_run(db):
    shoe = _shoe(db)
    rotation.log_run(db, shoe.id, distance_km=8.0, run_date=date(2026, 7, 2), source="coros")
    from app.services import activities as activities_svc
    items = activities_svc.unified_activities(db)
    assert len(items) == 1
    assert items[0].source == "coros"
    assert items[0].shoe.id == shoe.id


def test_coros_dedup_on_activity_coros_id(db):
    shoe = _shoe(db)
    first = coros_svc.confirm_run(
        db, coros_activity_id="abc", owned_shoe_id=shoe.id,
        run_date=date(2026, 7, 3), distance_km=6.0,
    )
    assert first is not None
    # Same COROS id again → idempotent no-op (dedup via activities.coros_activity_id).
    again = coros_svc.confirm_run(
        db, coros_activity_id="abc", owned_shoe_id=shoe.id,
        run_date=date(2026, 7, 3), distance_km=6.0,
    )
    assert again is None
    assert db.query(Activity).filter(Activity.coros_activity_id == "abc").count() == 1


def test_coros_confirm_populates_richer_activity_fields(db):
    # R2.7 T2 — the sync path now stores fields it used to discard.
    shoe = _shoe(db)
    result = coros_svc.confirm_run(
        db, coros_activity_id="rich1", owned_shoe_id=shoe.id,
        run_date=date(2026, 7, 4), distance_km=12.0, avg_pace="4:30/km",
        name="Morning Tempo", elevation_gain_m=85.0, moving_time_s=3240,
        elapsed_time_s=3300, avg_cadence=182.0, calories=780.0,
        training_load=120.5, training_focus="Lactate threshold",
        activity_tag="Tempo",
    )
    assert result is not None
    act = result.activity
    assert act.name == "Morning Tempo"
    assert act.elevation_gain_m == 85.0
    assert act.moving_time_s == 3240
    assert act.elapsed_time_s == 3300
    assert act.avg_cadence == 182.0
    assert act.calories == 780.0
    assert act.training_load == 120.5
    assert act.training_focus == "Lactate threshold"
    assert act.activity_tag == "Tempo"


def test_coros_confirm_leaves_new_fields_null_when_omitted(db):
    shoe = _shoe(db)
    result = coros_svc.confirm_run(
        db, coros_activity_id="bare1", owned_shoe_id=shoe.id,
        run_date=date(2026, 7, 5), distance_km=8.0,
    )
    act = result.activity
    assert act.training_load is None
    assert act.activity_tag is None
    assert act.elevation_gain_m is None


def test_delete_run_removes_manual_activity_and_reverts_mileage(db):
    shoe = _shoe(db, mileage=50.0)
    rotation.log_run(db, shoe.id, distance_km=10.0, run_date=date(2026, 7, 1), source="manual")
    attr = db.query(ShoeRun).one()

    rotation.delete_run(db, attr.id)
    assert db.query(ShoeRun).count() == 0
    assert db.query(Activity).count() == 0            # manual activity torn down
    assert db.query(OwnedShoe).one().current_mileage == pytest.approx(50.0)


def test_delete_run_keeps_strava_archive(db):
    shoe = _shoe(db, mileage=20.0)
    # A strava-source activity attributed to the shoe (as the migration produces).
    act = Activity(source="strava", activity_type="Run", strava_activity_id=999,
                   run_date=date(2026, 6, 1), distance_km=12.0)
    db.add(act)
    db.flush()
    attr = ShoeRun(activity_id=act.id, owned_shoe_id=shoe.id)
    db.add(attr)
    shoe.current_mileage += 12.0
    db.commit()

    rotation.delete_run(db, attr.id)
    assert db.query(ShoeRun).count() == 0              # attribution removed
    assert db.query(Activity).filter(Activity.id == act.id).count() == 1  # archive kept
    assert db.query(OwnedShoe).one().current_mileage == pytest.approx(20.0)


def test_lifetime_stats_read_through_join(db):
    shoe = _shoe(db)
    rotation.log_run(db, shoe.id, distance_km=10.0, run_date=date(2026, 7, 1),
                     source="manual", avg_pace="4:00/km", avg_hr=140)
    rotation.log_run(db, shoe.id, distance_km=10.0, run_date=date(2026, 7, 2),
                     source="manual", avg_pace="5:00/km", avg_hr=160)
    stats = rotation.compute_lifetime_stats(db, shoe.id)
    assert stats.total_runs == 2
    assert stats.lifetime_avg_pace == "4:30/km"   # mean of 240s and 300s
    assert stats.lifetime_avg_hr == 150


def test_shoe_run_has_no_run_field_proxies():
    # Proxies retired 2026-10-10: misuse (e.g. .filter(ShoeRun.distance_km)) must
    # fail loudly instead of silently doing nothing.
    for name in ("distance_km", "run_date", "source", "avg_hr",
                 "coros_activity_id", "notes", "avg_pace"):
        assert not hasattr(ShoeRun, name), name


def test_run_list_query_is_bounded_and_payload_matches_activity(db):
    from sqlalchemy import event
    from sqlalchemy.orm import contains_eager

    shoe = _shoe(db)
    for d in range(1, 6):
        rotation.log_run(db, shoe.id, distance_km=5.0 + d, run_date=date(2026, 7, d),
                         source="manual", avg_pace="5:00/km", avg_hr=150, notes=f"n{d}")
    shoe_id = shoe.id
    db.expire_all()

    stmts = []
    engine = db.get_bind()
    hook = lambda conn, cur, stmt, *a: stmts.append(stmt)
    event.listen(engine, "before_cursor_execute", hook)
    try:
        runs = (db.query(ShoeRun).join(Activity, ShoeRun.activity_id == Activity.id)
                .options(contains_eager(ShoeRun.activity))
                .filter(ShoeRun.owned_shoe_id == shoe_id).all())
        payloads = [rotation.shoe_run_payload(r) for r in runs]
    finally:
        event.remove(engine, "before_cursor_execute", hook)

    assert len(stmts) == 1, stmts      # eager-loaded: no per-row lazy loads
    assert len(payloads) == 5
    p = sorted(payloads, key=lambda x: x["run_date"])[0]
    assert (p["distance_km"], p["avg_pace"], p["avg_hr"], p["source"], p["notes"]) == (6.0, "5:00/km", 150, "manual", "n1")
