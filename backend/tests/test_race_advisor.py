"""
Tests for services/race_advisor.py (R3.6).

Covers: next-race selection (soonest future, completed excluded), weeks_to_race
calculation, avg_weekly_km computation, pipeline inclusion, fitness snapshot
presence/absence, weeks_back truncation, and no-race fallback.
All tests inject a fixed `today` so the suite is clock-independent.
"""
from datetime import date, datetime, timedelta

import pytest

from app.models.models import Activity, AthleteMetric, OwnedShoe, PlannedRace, ShoeRun
from app.services.race_advisor import race_block_context


# ── helpers ──────────────────────────────────────────────────────────────────

TODAY = date(2026, 7, 10)


def _race(db, name, days_ahead, *, distance_km=42.195, target_time_s=None,
          status="upcoming"):
    r = PlannedRace(
        name=name,
        race_date=TODAY + timedelta(days=days_ahead),
        distance_km=distance_km,
        target_time_s=target_time_s,
        status=status,
    )
    db.add(r)
    db.flush()
    return r


def _run(db, run_date, distance_km, *, shoe_id=None, source="coros",
         avg_pace_s=None, avg_hr=None):
    a = Activity(
        source=source, activity_type="Run", run_date=run_date,
        distance_km=distance_km, avg_pace_s_per_km=avg_pace_s, avg_hr=avg_hr,
    )
    db.add(a)
    db.flush()
    if shoe_id is not None:
        db.add(ShoeRun(activity_id=a.id, owned_shoe_id=shoe_id))
        db.flush()
    return a


def _shoe(db, brand="Nike", model="Vaporfly", *, mileage=0.0, limit=None,
          status="active", shoe_type=None):
    s = OwnedShoe(
        brand=brand, model=model, shoe_type=shoe_type, status=status,
        current_mileage=mileage, mileage_limit=limit,
    )
    db.add(s)
    db.flush()
    return s


def _fitness(db, *, vo2max=None, threshold_pace_s=None, predictions=None,
             running_level=None, captured_at=None):
    snap = AthleteMetric(
        vo2max=vo2max,
        threshold_pace_s_per_km=threshold_pace_s,
        race_predictions=predictions,
        running_level=running_level,
        captured_at=captured_at or datetime.utcnow(),
    )
    db.add(snap)
    db.flush()
    return snap


# ── tests: race selection ─────────────────────────────────────────────────────

def test_no_upcoming_race(db):
    ctx = race_block_context(db, today=TODAY)
    assert ctx.has_next_race is False
    assert ctx.next_race is None


def test_soonest_race_selected(db):
    _race(db, "Ottawa Marathon", 60)
    _race(db, "5k Tune-up", 14)
    ctx = race_block_context(db, today=TODAY)
    assert ctx.has_next_race is True
    assert ctx.next_race.name == "5k Tune-up"
    assert ctx.next_race.days_to_race == 14
    assert ctx.next_race.weeks_to_race == 2


def test_completed_race_excluded(db):
    _race(db, "Past Race", 30, status="completed")
    ctx = race_block_context(db, today=TODAY)
    assert ctx.has_next_race is False


def test_past_race_excluded(db):
    # days_ahead = -1 means yesterday
    _race(db, "Yesterday Race", -1)
    ctx = race_block_context(db, today=TODAY)
    assert ctx.has_next_race is False


def test_target_pace_present(db):
    # 42.195 km in 9420 s ≈ 3:43/km
    _race(db, "Ottawa Marathon", 60, distance_km=42.195, target_time_s=9420)
    ctx = race_block_context(db, today=TODAY)
    assert ctx.next_race.target_pace is not None
    assert ctx.next_race.target_time_s == 9420


# ── tests: weekly volumes ────────────────────────────────────────────────────

def test_avg_weekly_km_empty(db):
    ctx = race_block_context(db, today=TODAY)
    assert ctx.avg_weekly_km == 0.0
    assert ctx.recent_weeks == []


def test_avg_weekly_km_computed(db):
    # Two runs on different Mondays (different ISO weeks)
    monday1 = TODAY - timedelta(days=TODAY.weekday())         # this week's Monday
    monday2 = monday1 - timedelta(weeks=1)                   # last week's Monday
    _run(db, monday1, 10.0)
    _run(db, monday2, 20.0)
    ctx = race_block_context(db, today=TODAY)
    # Each week is one bucket; avg = (10 + 20) / 2 = 15
    assert ctx.avg_weekly_km == 15.0


def test_weeks_back_truncation(db):
    # Generate 20 weeks of runs (one per week) and ask for only 5
    for i in range(20):
        run_date = TODAY - timedelta(weeks=i)
        _run(db, run_date, 10.0)
    ctx = race_block_context(db, today=TODAY, weeks_back=5)
    assert len(ctx.recent_weeks) <= 5


# ── tests: pipeline ──────────────────────────────────────────────────────────

def test_pipeline_empty_no_shoes(db):
    ctx = race_block_context(db, today=TODAY)
    assert ctx.pipeline == []


def test_pipeline_includes_over_threshold(db):
    _shoe(db, mileage=800.0, limit=1000.0, shoe_type="Daily Trainer")
    ctx = race_block_context(db, today=TODAY)
    assert len(ctx.pipeline) == 1
    p = ctx.pipeline[0]
    assert p.pct >= 0.75
    assert p.shoe_type == "Daily Trainer"


def test_pipeline_excludes_below_threshold(db):
    _shoe(db, mileage=400.0, limit=1000.0)
    ctx = race_block_context(db, today=TODAY)
    assert ctx.pipeline == []


# ── tests: fitness ────────────────────────────────────────────────────────────

def test_no_fitness_when_no_snapshot(db):
    ctx = race_block_context(db, today=TODAY)
    assert ctx.has_fitness is False
    assert ctx.fitness is None


def test_fitness_snapshot_included(db):
    _fitness(db, vo2max=62.5, threshold_pace_s=223, running_level=8.5)
    ctx = race_block_context(db, today=TODAY)
    assert ctx.has_fitness is True
    f = ctx.fitness
    assert f.vo2max == 62.5
    assert f.threshold_pace is not None  # formatted as "M:SS/km"
    assert f.running_level == 8.5


def test_fitness_race_predictions_preserved(db):
    predictions = {"5.0": 1200, "10.0": 2500, "42.195": 9420}
    _fitness(db, predictions=predictions)
    ctx = race_block_context(db, today=TODAY)
    assert ctx.fitness.race_predictions == predictions
