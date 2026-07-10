"""
Tests for services/weekly_summary.py (R3.1).

Covers: volume this-vs-last-week, per-shoe grouping and km-descending order,
shoe_type enrichment, notable-run tag filtering, pipeline inclusion threshold,
checkpoint detection (this week vs. prior week), next-race selection.
All tests inject a fixed `today` so the suite is clock-independent.
"""
from datetime import date, datetime, timedelta

import pytest

from app.models.models import Activity, OwnedShoe, PlannedRace, ShoeNote, ShoeRun
from app.services.weekly_summary import NOTABLE_TAGS, weekly_summary


# ── helpers ──────────────────────────────────────────────────────────────────

def _shoe(db, brand="Nike", model="Vaporfly", *, mileage=0.0, limit=None,
          status="active", shoe_type=None, nickname=None):
    s = OwnedShoe(
        brand=brand, model=model, nickname=nickname, shoe_type=shoe_type,
        current_mileage=mileage, mileage_limit=limit, status=status,
    )
    db.add(s)
    db.flush()
    return s


def _run(db, shoe_id, run_date, distance_km, *, source="coros",
         avg_pace_s=None, avg_hr=None, activity_tag=None, name=None):
    a = Activity(
        source=source, activity_type="Run", run_date=run_date,
        distance_km=distance_km, avg_pace_s_per_km=avg_pace_s,
        avg_hr=avg_hr, activity_tag=activity_tag, name=name,
    )
    db.add(a)
    db.flush()
    if shoe_id is not None:
        db.add(ShoeRun(activity_id=a.id, owned_shoe_id=shoe_id))
        db.flush()
    return a


def _note(db, shoe_id, mileage_at, *, triggered_by="checkpoint",
          created_at=None):
    n = ShoeNote(
        owned_shoe_id=shoe_id,
        body=f"Crossed {mileage_at}km",
        mileage_at_note=mileage_at,
        triggered_by=triggered_by,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(n)
    db.flush()
    return n


def _race(db, name, race_date, *, distance_km=42.195, target_time_s=None, status="upcoming"):
    r = PlannedRace(
        name=name, race_date=race_date, distance_km=distance_km,
        target_time_s=target_time_s, status=status,
    )
    db.add(r)
    db.flush()
    return r


# Anchor: a fixed Monday so every test is deterministic
TODAY = date(2026, 7, 9)                               # Thursday
THIS_MONDAY = date(2026, 7, 6)                         # Monday of the same week
LAST_MONDAY = THIS_MONDAY - timedelta(days=7)          # Monday of prior week


def _last_monday() -> date:
    return LAST_MONDAY


# ── volume ───────────────────────────────────────────────────────────────────

def test_volume_this_and_last_week(db):
    shoe = _shoe(db)
    _run(db, shoe.id, THIS_MONDAY, 10.0)
    _run(db, shoe.id, THIS_MONDAY + timedelta(days=2), 5.0)    # Wednesday
    _run(db, shoe.id, _last_monday(), 8.0)                     # last Monday

    s = weekly_summary(db, today=TODAY)

    assert s.this_week_km == 15.0
    assert s.last_week_km == 8.0
    assert s.delta_km == 7.0


def test_empty_week_reads_zero(db):
    shoe = _shoe(db)
    # Only a run three weeks ago — should not affect this or last week
    _run(db, shoe.id, THIS_MONDAY - timedelta(days=21), 12.0)

    s = weekly_summary(db, today=TODAY)

    assert s.this_week_km == 0.0
    assert s.last_week_km == 0.0
    assert s.delta_km == 0.0


def test_run_on_sunday_counts_in_this_week(db):
    shoe = _shoe(db)
    this_sunday = THIS_MONDAY + timedelta(days=6)
    _run(db, shoe.id, this_sunday, 20.0)

    s = weekly_summary(db, today=TODAY)

    assert s.this_week_km == 20.0


def test_unattributed_run_counts_in_volume(db):
    # A run with no shoe still contributes to weekly km
    _run(db, None, THIS_MONDAY, 7.5)

    s = weekly_summary(db, today=TODAY)

    assert s.this_week_km == 7.5
    assert s.per_shoe_usage == []   # nothing attributed


# ── per-shoe usage ────────────────────────────────────────────────────────────

def test_per_shoe_usage_groups_by_shoe(db):
    shoe_a = _shoe(db, brand="Adidas", model="Adios Pro 4", shoe_type="long_distance_racer")
    shoe_b = _shoe(db, brand="Nike", model="Pegasus 41", shoe_type="daily_trainer")
    _run(db, shoe_a.id, THIS_MONDAY, 10.0)
    _run(db, shoe_a.id, THIS_MONDAY + timedelta(days=1), 5.0)
    _run(db, shoe_b.id, THIS_MONDAY + timedelta(days=2), 8.0)

    s = weekly_summary(db, today=TODAY)

    assert len(s.per_shoe_usage) == 2
    # km-descending: Adios Pro 4 (15km) before Pegasus (8km)
    assert s.per_shoe_usage[0].shoe_id == shoe_a.id
    assert s.per_shoe_usage[0].km_this_week == 15.0
    assert s.per_shoe_usage[0].run_count == 2
    assert s.per_shoe_usage[0].shoe_type == "long_distance_racer"

    assert s.per_shoe_usage[1].shoe_id == shoe_b.id
    assert s.per_shoe_usage[1].km_this_week == 8.0
    assert s.per_shoe_usage[1].run_count == 1


def test_last_week_runs_not_in_per_shoe_usage(db):
    shoe = _shoe(db)
    _run(db, shoe.id, _last_monday(), 10.0)   # last week — excluded

    s = weekly_summary(db, today=TODAY)

    assert s.per_shoe_usage == []


# ── notable runs ──────────────────────────────────────────────────────────────

def test_notable_run_tags_are_included(db):
    shoe = _shoe(db)
    for tag in NOTABLE_TAGS:
        _run(db, shoe.id, THIS_MONDAY, 10.0, activity_tag=tag)

    s = weekly_summary(db, today=TODAY)

    returned_tags = {n.activity_tag for n in s.notable_runs}
    assert returned_tags == NOTABLE_TAGS


def test_easy_recovery_workout_not_notable(db):
    shoe = _shoe(db)
    for tag in ("Easy", "Recovery", "Workout"):
        _run(db, shoe.id, THIS_MONDAY, 6.0, activity_tag=tag)

    s = weekly_summary(db, today=TODAY)

    assert s.notable_runs == []


def test_untagged_run_not_notable(db):
    shoe = _shoe(db)
    _run(db, shoe.id, THIS_MONDAY, 6.0)   # no tag

    s = weekly_summary(db, today=TODAY)

    assert s.notable_runs == []


def test_notable_run_carries_shoe_label(db):
    shoe = _shoe(db, brand="Adidas", model="Adios Pro 4", nickname="Race Day")
    _run(db, shoe.id, THIS_MONDAY, 21.1, activity_tag="Race")

    s = weekly_summary(db, today=TODAY)

    assert len(s.notable_runs) == 1
    assert s.notable_runs[0].shoe == "Adidas Adios Pro 4 (Race Day)"


# ── retirement pipeline ───────────────────────────────────────────────────────

def test_shoe_at_75_pct_in_pipeline(db):
    # exactly 75% — should be included (threshold is ≥ 0.75)
    _shoe(db, mileage=600.0, limit=800.0, shoe_type="daily_trainer")

    s = weekly_summary(db, today=TODAY)

    assert len(s.pipeline) == 1
    assert abs(s.pipeline[0].pct - 0.75) < 0.001


def test_shoe_below_75_pct_not_in_pipeline(db):
    _shoe(db, mileage=599.0, limit=800.0)

    s = weekly_summary(db, today=TODAY)

    assert s.pipeline == []


def test_shoe_without_limit_not_in_pipeline(db):
    _shoe(db, mileage=900.0, limit=None)   # no limit set

    s = weekly_summary(db, today=TODAY)

    assert s.pipeline == []


def test_pipeline_worst_first(db):
    _shoe(db, model="A", mileage=700.0, limit=800.0)   # 87.5%
    _shoe(db, model="B", mileage=650.0, limit=800.0)   # 81.25%

    s = weekly_summary(db, today=TODAY)

    assert len(s.pipeline) == 2
    assert s.pipeline[0].pct > s.pipeline[1].pct


# ── checkpoints ──────────────────────────────────────────────────────────────

def test_checkpoint_this_week_included(db):
    shoe = _shoe(db, brand="Nike", model="Pegasus")
    # Timestamp within this ISO week
    this_week_dt = datetime.combine(THIS_MONDAY + timedelta(days=1), datetime.min.time())
    _note(db, shoe.id, 400.0, created_at=this_week_dt)

    s = weekly_summary(db, today=TODAY)

    assert len(s.checkpoints_this_week) == 1
    assert s.checkpoints_this_week[0].checkpoint_km == 400
    assert s.checkpoints_this_week[0].brand == "Nike"


def test_checkpoint_last_week_excluded(db):
    shoe = _shoe(db)
    last_week_dt = datetime.combine(_last_monday(), datetime.min.time())
    _note(db, shoe.id, 300.0, created_at=last_week_dt)

    s = weekly_summary(db, today=TODAY)

    assert s.checkpoints_this_week == []


def test_manual_note_not_a_checkpoint(db):
    shoe = _shoe(db)
    this_week_dt = datetime.combine(THIS_MONDAY, datetime.min.time())
    _note(db, shoe.id, 200.0, triggered_by="manual", created_at=this_week_dt)

    s = weekly_summary(db, today=TODAY)

    assert s.checkpoints_this_week == []


# ── next race ─────────────────────────────────────────────────────────────────

def test_next_race_is_soonest_upcoming(db):
    _race(db, "Ottawa Marathon", TODAY + timedelta(days=90), distance_km=42.195)
    _race(db, "10k tune-up", TODAY + timedelta(days=14), distance_km=10.0)

    s = weekly_summary(db, today=TODAY)

    assert s.next_race is not None
    assert s.next_race.name == "10k tune-up"
    assert s.next_race.days_remaining == 14


def test_no_upcoming_race_is_none(db):
    # Only a completed past race
    _race(db, "Past Race", TODAY - timedelta(days=10), status="completed")

    s = weekly_summary(db, today=TODAY)

    assert s.next_race is None


def test_week_summary_fields(db):
    # Confirm the ISO week boundaries are correct for TODAY = Thu 2026-07-09
    s = weekly_summary(db, today=TODAY)

    assert s.week_start == "2026-07-06"   # Monday
    assert s.week_end == "2026-07-12"     # Sunday
