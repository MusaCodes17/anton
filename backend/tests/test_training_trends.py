"""R8.4.2 — "building or holding?": load trend + the Volume chart's rolling line.

Rules under test: the verdict thresholds at their exact boundaries (1.10 and
0.90 are holding), the window edges (as_of and as_of-6 are the last 7 days;
as_of-34 is the oldest prior day), taper only inside 21 days of a still-planned
race, no baseline without prior running, non-runs ignored, and the weekly
rolling average counting empty weeks as 0 and looking back past a range cut.
All tests pin `as_of` so the suite is clock-independent.
"""
import asyncio
from contextlib import contextmanager
from datetime import date, timedelta

import pytest

from app import mcp_server
from app.models.models import Activity, PlannedRace
from app.routers.training import get_training_trends
from app.services import strava_stats
from app.services.training_trends import load_trend

AS_OF = date(2026, 10, 9)          # a Friday


def run(db, day, km, activity_type="Run"):
    db.add(Activity(source="manual", activity_type=activity_type, run_date=day, distance_km=km))
    db.commit()


def baseline(db, week_km=50.0):
    """A steady prior 28 days: 4 × `week_km`, one run per prior week."""
    for k in range(4):
        run(db, AS_OF - timedelta(days=7 + 7 * k + 1), week_km)


def race(db, days_ahead, status="planned", name="Beneva Marathon"):
    db.add(PlannedRace(name=name, race_date=AS_OF + timedelta(days=days_ahead),
                       distance_km=42.195, status=status))
    db.commit()


# --- verdict thresholds --------------------------------------------------------------

@pytest.mark.parametrize("last7,verdict,ratio", [
    (55.5, "building", 1.11),
    (55.0, "holding", 1.10),          # exactly 1.10 is holding (strictly-above rule)
    (50.0, "holding", 1.00),
    (45.0, "holding", 0.90),          # exactly 0.90 is holding
    (44.5, "easing", 0.89),
])
def test_verdict_boundaries(db, last7, verdict, ratio):
    baseline(db)
    run(db, AS_OF, last7)
    t = load_trend(db, as_of=AS_OF)
    assert (t.verdict, t.ratio) == (verdict, ratio)
    assert t.prior_avg_week_km == 50.0 and t.heuristic is True


def test_window_edges(db):
    run(db, AS_OF, 10)                              # today counts
    run(db, AS_OF - timedelta(days=6), 12)          # oldest acute day
    run(db, AS_OF - timedelta(days=7), 20)          # newest prior day
    run(db, AS_OF - timedelta(days=34), 8)          # oldest prior day
    run(db, AS_OF - timedelta(days=35), 99)         # outside both windows
    run(db, AS_OF + timedelta(days=1), 99)          # after as_of
    t = load_trend(db, as_of=AS_OF)
    assert (t.last7_km, t.last7_runs, t.last7_longest_km) == (22.0, 2, 12.0)
    assert (t.prior_avg_week_km, t.prior_longest_km) == (7.0, 20.0)


def test_non_runs_are_ignored(db):
    baseline(db)
    run(db, AS_OF, 50)
    run(db, AS_OF, 80, activity_type="Ride")
    assert load_trend(db, as_of=AS_OF).last7_km == 50.0


def test_no_prior_running_is_no_baseline_not_building(db):
    run(db, AS_OF, 30)
    t = load_trend(db, as_of=AS_OF)
    assert (t.verdict, t.ratio, t.last7_km) == ("no_baseline", None, 30.0)


def test_no_runs_at_all(db):
    t = load_trend(db, as_of=AS_OF)
    assert (t.verdict, t.last7_km, t.last7_longest_km) == ("no_baseline", 0.0, 0.0)


# --- taper ---------------------------------------------------------------------------

def test_easing_within_three_weeks_of_a_planned_race_is_taper(db):
    baseline(db)
    run(db, AS_OF, 30)
    race(db, 21)                                    # day 21 is inside the window
    t = load_trend(db, as_of=AS_OF)
    assert t.verdict == "taper"
    assert (t.taper_race.name, t.taper_race.days_to_race) == ("Beneva Marathon", 21)


def test_race_day_itself_counts_for_taper(db):
    baseline(db)
    race(db, 0)
    assert load_trend(db, as_of=AS_OF).verdict == "taper"


@pytest.mark.parametrize("days_ahead,status", [
    (22, "planned"),          # just outside 3 weeks
    (-1, "planned"),          # already past
    (10, "skipped"),
    (10, "completed"),
])
def test_easing_without_a_qualifying_race_stays_easing(db, days_ahead, status):
    baseline(db)
    run(db, AS_OF, 30)
    race(db, days_ahead, status=status)
    t = load_trend(db, as_of=AS_OF)
    assert t.verdict == "easing" and t.taper_race is None


def test_building_close_to_a_race_is_still_building(db):
    baseline(db)
    run(db, AS_OF, 70)
    race(db, 7)
    assert load_trend(db, as_of=AS_OF).verdict == "building"


# --- REST + MCP parity -------------------------------------------------------------------

def test_endpoint_and_mcp_tool_agree(db, monkeypatch):
    baseline(db)
    run(db, AS_OF, 30)
    race(db, 2)

    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server, "get_session", fake_session)

    rest = get_training_trends(as_of=AS_OF, db=db).model_dump()["load"]
    mcp = mcp_server.get_training_trends(as_of=AS_OF.isoformat())["load"]
    assert rest == mcp
    assert rest["verdict"] == "taper" and rest["taper_race"]["race_date"] == "2026-10-11"
    assert rest["building_above"] == 1.1 and rest["easing_below"] == 0.9


def test_mcp_tool_rejects_a_bad_date():
    assert "error" in mcp_server.get_training_trends(as_of="next friday")


# --- Volume chart rolling line -------------------------------------------------------------

def _weekly(db, **kw):
    return {b.period: b for b in strava_stats.training_summary(db, "weekly", **kw)}


def test_rolling_average_counts_empty_weeks_as_zero(db):
    # Mondays of four consecutive ISO weeks; the second week has no running.
    w1 = date(2026, 9, 7)
    run(db, w1, 40)
    run(db, w1 + timedelta(weeks=2), 20)
    run(db, w1 + timedelta(weeks=3), 60)
    weeks = _weekly(db)
    assert weeks["2026-W37"].rolling_4wk_km == 10.0               # (40 + 0 + 0 + 0) / 4
    assert weeks["2026-W40"].rolling_4wk_km == 30.0               # (40 + 0 + 20 + 60) / 4
    assert "2026-W38" not in weeks                                 # empty week still has no bucket


def test_rolling_average_looks_back_past_the_range_start(db):
    w1 = date(2026, 9, 7)
    for k in range(4):
        run(db, w1 + timedelta(weeks=k), 40)
    # Range starts on the Wednesday of the 4th week: that week's bucket only
    # holds runs in range, but its rolling value covers the 3 weeks before.
    run(db, w1 + timedelta(weeks=3, days=3), 8)
    weeks = _weekly(db, date_from=w1 + timedelta(weeks=3, days=2))
    assert list(weeks) == ["2026-W40"]
    assert weeks["2026-W40"].total_km == 8.0
    assert weeks["2026-W40"].rolling_4wk_km == 42.0               # (40 + 40 + 40 + 48) / 4


def test_monthly_buckets_have_no_rolling_value(db):
    run(db, AS_OF, 10)
    assert all(b.rolling_4wk_km is None for b in strava_stats.training_summary(db, "monthly"))
