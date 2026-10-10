"""R8.4.3 — "what's my form now?": the form trend.

Rules under test: the steady-run filter at its edges (no-HR runs never count;
exactly 5 km and exactly 1.2× elapsed/moving are in; tags other than Easy /
Long Run are out), the verdict thresholds at their exact boundaries (±3.0% is
steady), the minimum steady runs per window (5 is enough, 4 is not), the
window edges (as_of-41 is recent, as_of-125 the oldest baseline day), monthly
points under 4 runs keeping their count but no value, the 90-day best efforts
agreeing with the Records card, and the COROS fitness line on Toronto dates.
All tests pin `as_of` so the suite is clock-independent.
"""
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import pytest

from app import mcp_server
from app.models.models import Activity, ActivityBestEffort, ActivityEffortScan, AthleteMetric
from app.routers.training import get_training_trends
from app.services import strava_stats
from app.services.activities import UnifiedActivity
from app.services.training_trends import form_trend, m_per_beat

AS_OF = date(2026, 10, 9)
RECENT_DAY = AS_OF - timedelta(days=10)      # inside the last 42 days
BASELINE_DAY = AS_OF - timedelta(days=60)    # inside the 84 days before them


def run(db, day, *, km=10.0, hr=150, moving_s=3000, elapsed_s=None, tag=None, activity_type="Run"):
    a = Activity(source="manual", activity_type=activity_type, run_date=day, distance_km=km,
                 avg_hr=hr, moving_time_s=moving_s, elapsed_time_s=elapsed_s, activity_tag=tag)
    db.add(a)
    db.commit()
    return a


def runs(db, day, n, **kw):
    for _ in range(n):
        run(db, day, **kw)


def ua(**kw):
    base = dict(date=AS_OF, distance_km=10.0, source="manual", avg_hr=150, moving_time_s=3000)
    base.update(kw)
    return UnifiedActivity(**base)


# --- steady-run filter ---------------------------------------------------------------

def test_metres_per_beat_is_distance_over_heartbeats():
    # 10 km in 50 min at 150 bpm = 10 000 m / 7 500 beats
    assert m_per_beat(ua()) == pytest.approx(1.3333, abs=1e-4)


@pytest.mark.parametrize("kw,steady", [
    ({"avg_hr": None}, False),                               # no HR: never counts
    ({"avg_hr": 0}, False),
    ({"distance_km": 4.99}, False),
    ({"distance_km": 5.0}, True),                            # exactly 5 km counts
    ({"activity_tag": "Easy"}, True),
    ({"activity_tag": "Long Run"}, True),
    ({"activity_tag": "Tempo"}, False),
    ({"activity_tag": "Race"}, False),
    ({"activity_tag": "Recovery"}, False),
    ({"elapsed_time_s": 3600}, True),                        # exactly 1.2× moving counts
    ({"elapsed_time_s": 3601}, False),                       # long stops
    ({"moving_time_s": None, "elapsed_time_s": 9000, "avg_pace_s_per_km": 300}, True),  # no moving clock: no stop check, pace gives time
    ({"moving_time_s": None, "avg_pace_s_per_km": None}, False),                         # no time at all
])
def test_steady_filter(kw, steady):
    assert (m_per_beat(ua(**kw)) is not None) is steady


def test_runs_without_hr_are_excluded_from_form(db):
    runs(db, BASELINE_DAY, 5)
    runs(db, RECENT_DAY, 5)
    runs(db, RECENT_DAY, 3, hr=None, moving_s=2000)          # fast, but no HR
    f = form_trend(db, as_of=AS_OF)
    assert (f.recent_steady_runs, f.baseline_steady_runs) == (5, 5)
    assert (f.verdict, f.change_pct) == ("steady", 0.0)


def test_non_runs_are_ignored(db):
    runs(db, BASELINE_DAY, 5)
    runs(db, RECENT_DAY, 5)
    run(db, RECENT_DAY, km=40, moving_s=3000, activity_type="Ride")
    assert form_trend(db, as_of=AS_OF).recent_steady_runs == 5


# --- verdict thresholds --------------------------------------------------------------

@pytest.mark.parametrize("base,recent,verdict,change", [
    ({"moving_s": 3100}, {"moving_s": 3000}, "improving", 3.3),
    ({"hr": 103}, {"hr": 100}, "steady", 3.0),                # exactly +3.0 is steady
    ({}, {}, "steady", 0.0),
    ({"hr": 97}, {"hr": 100}, "steady", -3.0),                # exactly −3.0 is steady
    ({"moving_s": 3000}, {"moving_s": 3100}, "slipping", -3.2),
])
def test_verdict_boundaries(db, base, recent, verdict, change):
    runs(db, BASELINE_DAY, 5, **base)
    runs(db, RECENT_DAY, 5, **recent)
    f = form_trend(db, as_of=AS_OF)
    assert (f.verdict, f.change_pct) == (verdict, change)
    assert f.heuristic is True and (f.improving_above_pct, f.slipping_below_pct) == (3.0, -3.0)


def test_verdict_uses_the_median_so_one_odd_run_cannot_swing_it(db):
    runs(db, BASELINE_DAY, 5)
    runs(db, RECENT_DAY, 4)
    run(db, RECENT_DAY, moving_s=1800)                       # an untagged race among steady runs
    assert form_trend(db, as_of=AS_OF).verdict == "steady"


@pytest.mark.parametrize("n_recent,n_base,verdict", [
    (5, 5, "steady"),                                        # exactly 5 per window is enough
    (4, 5, "not_enough_data"),
    (5, 4, "not_enough_data"),
])
def test_minimum_steady_runs_per_window(db, n_recent, n_base, verdict):
    runs(db, BASELINE_DAY, n_base)
    runs(db, RECENT_DAY, n_recent)
    f = form_trend(db, as_of=AS_OF)
    assert f.verdict == verdict
    assert (f.change_pct is None) is (verdict == "not_enough_data")
    assert (f.recent_steady_runs, f.baseline_steady_runs) == (n_recent, n_base)


def test_window_edges(db):
    run(db, AS_OF)                                           # today counts
    run(db, AS_OF - timedelta(days=41))                      # oldest recent day
    run(db, AS_OF - timedelta(days=42))                      # newest baseline day
    run(db, AS_OF - timedelta(days=125))                     # oldest baseline day
    run(db, AS_OF - timedelta(days=126))                     # outside both
    run(db, AS_OF + timedelta(days=1))                       # after as_of
    f = form_trend(db, as_of=AS_OF)
    assert (f.recent_steady_runs, f.baseline_steady_runs) == (2, 2)


def test_no_runs_at_all(db):
    f = form_trend(db, as_of=AS_OF)
    assert (f.verdict, f.change_pct, f.recent_m_per_beat) == ("not_enough_data", None, None)
    assert len(f.months) == 12 and all(m.m_per_beat is None for m in f.months)
    assert [(b.label, b.recent, b.all_time) for b in f.best_efforts] == [("5k", None, None), ("10k", None, None)]
    assert f.fitness == []


# --- monthly chart -------------------------------------------------------------------

def test_months_cover_twelve_months_oldest_first_with_a_minimum(db):
    runs(db, date(2026, 10, 1), 4)                           # 4 steady runs: a value
    runs(db, date(2026, 9, 3), 3)                            # 3: count kept, no value
    run(db, date(2025, 10, 31))                              # 2025-10 is outside the 12 months
    f = form_trend(db, as_of=AS_OF)
    assert [m.month for m in f.months][0] == "2025-11" and f.months[-1].month == "2026-10"
    by = {m.month: m for m in f.months}
    assert (by["2026-10"].steady_runs, by["2026-10"].m_per_beat) == (4, 1.333)
    assert (by["2026-09"].steady_runs, by["2026-09"].m_per_beat) == (3, None)
    assert by["2026-08"].steady_runs == 0
    assert f.min_month_runs == 4


def test_month_value_is_the_median(db):
    for moving_s in (3000, 3000, 3000, 3000, 1500):          # one race-pace outlier
        run(db, date(2026, 8, 5), moving_s=moving_s)
    by = {m.month: m for m in form_trend(db, as_of=AS_OF).months}
    assert by["2026-08"].m_per_beat == 1.333


# --- 90-day best efforts -------------------------------------------------------------

def segment(db, activity, label, elapsed_s):
    db.add(ActivityBestEffort(activity_id=activity.id, distance_label=label,
                              elapsed_s=elapsed_s, start_offset_m=0, source="fit"))
    if not db.get(ActivityEffortScan, activity.id):
        db.add(ActivityEffortScan(activity_id=activity.id, status="ok", source="fit"))
    db.commit()


def _best(f, label):
    return next(b for b in f.best_efforts if b.label == label)


def test_rolling_best_vs_all_time(db):
    old = run(db, AS_OF - timedelta(days=90), tag="Race")    # day 90 is outside the 90-day window
    segment(db, old, "5k", 1000)                             # 3:20/km — all-time
    new = run(db, AS_OF - timedelta(days=89))                # day 89 is inside
    segment(db, new, "5k", 1050)                             # 3:30/km
    f = form_trend(db, as_of=AS_OF)
    five = _best(f, "5k")
    assert (five.recent.time_s, five.recent.activity_id, five.recent.segment) == (1050, new.id, True)
    assert (five.all_time.time_s, five.all_time.pace_s_per_km) == (1000, 200)
    assert five.pct_off_all_time == 5.0
    assert five.target_km == 5.0
    ten = _best(f, "10k")
    assert (ten.recent, ten.pct_off_all_time) == (None, None)


def test_recent_best_that_is_the_all_time_best_reads_zero(db):
    a = run(db, AS_OF - timedelta(days=3))
    segment(db, a, "10k", 2100)
    ten = _best(form_trend(db, as_of=AS_OF), "10k")
    assert (ten.recent.time_s, ten.all_time.time_s, ten.pct_off_all_time) == (2100, 2100, 0.0)


def test_unscanned_whole_run_competes_on_pace_like_the_records_card(db):
    scanned = run(db, AS_OF - timedelta(days=20))
    segment(db, scanned, "5k", 1100)                         # 3:40/km
    whole = run(db, AS_OF - timedelta(days=10), km=5.2, moving_s=1090, elapsed_s=1100)   # 3:31.5/km, unscanned
    five = _best(form_trend(db, as_of=AS_OF), "5k")
    assert (five.recent.activity_id, five.recent.segment, five.recent.distance_km) == (whole.id, False, 5.2)
    # Same answer as the Records card (as_of after every run).
    card = next(b for b in strava_stats.personal_bests(db).best_efforts if b.band == "5k")
    assert (five.all_time.activity_id, five.all_time.time_s) == (card.activity_id, card.total_time_s)


def test_runs_after_as_of_are_not_bests_yet(db):
    later = run(db, AS_OF + timedelta(days=1))
    segment(db, later, "5k", 900)
    five = _best(form_trend(db, as_of=AS_OF), "5k")
    assert five.all_time is None


# --- fitness line ----------------------------------------------------------------------

def test_fitness_line_is_toronto_dated_ordered_and_stops_at_as_of(db):
    db.add_all([
        AthleteMetric(vo2max=60.0, threshold_pace_s_per_km=205, captured_at=datetime(2026, 9, 1, 12, 0)),
        # 03:20 UTC on the 10th is 23:20 on the 9th in Toronto: counts for as_of.
        AthleteMetric(vo2max=61.0, threshold_pace_s_per_km=202, running_level=97.0,
                      captured_at=datetime(2026, 10, 10, 3, 20)),
        AthleteMetric(vo2max=60.5, captured_at=datetime(2026, 9, 1, 20, 0)),   # same day, later: wins
        AthleteMetric(vo2max=62.0, captured_at=datetime(2026, 10, 10, 12, 0)),  # after as_of
    ])
    db.commit()
    line = form_trend(db, as_of=AS_OF).fitness
    assert [(p.captured_date, p.vo2max) for p in line] == [("2026-09-01", 60.5), ("2026-10-09", 61.0)]
    assert (line[1].threshold_pace_s_per_km, line[1].running_level) == (202, 97.0)


# --- REST + MCP parity -------------------------------------------------------------------

def test_endpoint_and_mcp_tool_agree_on_form(db, monkeypatch):
    runs(db, BASELINE_DAY, 5, moving_s=3100)
    runs(db, RECENT_DAY, 5)
    segment(db, run(db, RECENT_DAY, tag="Race"), "5k", 1000)
    db.add(AthleteMetric(vo2max=61.0, captured_at=datetime(2026, 9, 1, 12, 0)))
    db.commit()

    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)

    rest = get_training_trends(as_of=AS_OF, db=db).model_dump()
    mcp = mcp_server.get_training_trends(as_of=AS_OF.isoformat())
    assert rest["form"] == mcp["form"] and rest["load"] == mcp["load"]
    assert rest["form"]["verdict"] == "improving"
    assert rest["form"]["best_efforts"][0]["recent"]["time_s"] == 1000
    assert rest["form"]["fitness"] == [{"captured_date": "2026-09-01", "vo2max": 61.0,
                                        "threshold_pace_s_per_km": None, "running_level": None}]
