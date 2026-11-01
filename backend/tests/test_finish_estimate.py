"""R11.7 — finish-time range, evidence grade and live backtest (finish_estimate).

Rules under test: the point estimate is the FASTEST Riegel equivalent of a
10k/half source (not the longest); excluded runs never count, even as race PBs;
a range needs MIN_HISTORY scored past races and equals estimate × (1 ± the
largest past error) exactly, widened ×1.5 when the evidence is thin; the grade
boundaries (spread exactly 4% is strong, exactly 10% is not thin, ages 42/56);
DNF, mismatched-distance and excluded past races are skipped with a reason and
never counted; a past race's backtest prediction is the same function run the
day before it, so it reproduces from as_of; planned-race classing; the COROS
figure comes from the latest snapshot on or before the evidence date; the
estimate rides on the readiness payload (REST == MCP).
"""
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pytest

from app import mcp_server
from app.models.models import Activity, AthleteMetric, PlannedRace
from app.routers.races import get_race_readiness
from app.services import finish_estimate as fe
from app.services import race_advisor
from app.services.race_advisor import race_readiness
from tests.test_race_readiness import AS_OF, RACE_DAY, effort, race, run

EVIDENCE_TO = AS_OF - timedelta(days=1)


def equiv(time_s, km, race_km):
    return round(time_s * (race_km / km) ** fe.RIEGEL_K)


def past_race(db, day, *, km=21.0975, result_s=5000, status="completed", link_km="same", name=None):
    """A past race row linked to a run (link_km=None: no linked run)."""
    act_id = None
    if link_km is not None:
        a = Activity(source="manual", activity_type="Run", run_date=day,
                     distance_km=km if link_km == "same" else link_km, elapsed_time_s=result_s)
        db.add(a)
        db.commit()
        act_id = a.id
    r = PlannedRace(name=name or f"Race {day}", race_date=day, distance_km=km, status=status,
                    result_time_s=result_s if status == "completed" else None, activity_id=act_id)
    db.add(r)
    db.commit()
    return r


def history(db, n=3, *, ten_k_s=(2400, 2450, 2500), actual_s=(5400, 5200, 5000)):
    """n past halves, ≥ 9 weeks apart, each with a 10k effort 8 days before it."""
    days = [date(2026, 1, 4) + timedelta(weeks=10 * i) for i in range(n)]
    for d, t, a in zip(days, ten_k_s, actual_s):
        effort(db, d - timedelta(days=8), "10k", t)
        past_race(db, d, result_s=a)
    return days


def est(db, km=42.195, target=None, evidence_to=EVIDENCE_TO, as_of=AS_OF):
    return fe.finish_estimate(db, race_distance_km=km, target_time_s=target,
                              as_of=as_of, evidence_to=evidence_to)


def src(band, km, age, equivalent_s):
    return fe.EstimateSource(kind="best_effort", band=band, distance_km=km, time_s=1, run_date="2026-01-01",
                             age_days=age, activity_id=None, name=None, segment=True, equivalent_s=equivalent_s)


# --- constants / classing ---------------------------------------------------------------

def test_evidence_window_matches_the_readiness_window():
    assert fe.EVIDENCE_WEEKS == race_advisor.RECENT_EFFORT_WEEKS


def test_10k_race_is_unsupported(db):
    r = est(db, km=10.0)
    assert r.state == "unsupported_distance" and r.estimate_s is None and r.low_s is None
    assert "10" in r.message


def test_planned_race_near_a_nominal_uses_the_nominal_km(db):
    effort(db, EVIDENCE_TO - timedelta(days=10), "10k", 2400)
    r = est(db, km=42.0)                       # within 5% of 42.195
    assert r.race_class == "marathon" and r.race_km == 42.195
    assert r.estimate_s == equiv(2400, 10.0, 42.195)


def test_a_race_with_no_distance_is_unsupported(db):
    assert est(db, km=None).state == "unsupported_distance"


# --- evidence ---------------------------------------------------------------------------

def test_no_10k_or_half_means_no_range(db):
    history(db)
    effort(db, EVIDENCE_TO - timedelta(days=5), "5k", 1100)   # a 5k alone can't set the estimate
    r = est(db)
    assert r.state == "insufficient_evidence" and r.estimate_s is None
    assert r.low_s is None and r.high_s is None and r.band_pct is None
    assert r.message == f"No 10k or half-marathon effort in the last 8 weeks (since {r.window_from})."
    assert [s.band for s in r.sources] == ["5k"]
    assert r.window_from == (EVIDENCE_TO - timedelta(weeks=8) + timedelta(days=1)).isoformat()


def test_old_evidence_falls_outside_the_window(db):
    history(db)
    effort(db, EVIDENCE_TO - timedelta(weeks=8), "10k", 2400)   # one day too old
    assert est(db).state == "insufficient_evidence"
    effort(db, EVIDENCE_TO - timedelta(weeks=8) + timedelta(days=1), "10k", 2400)   # first day in
    assert est(db).estimate_s == equiv(2400, 10.0, 42.195)


def test_fastest_equivalent_wins_over_the_longest_source(db):
    history(db)
    effort(db, EVIDENCE_TO - timedelta(days=10), "10k", 2400)
    effort(db, EVIDENCE_TO - timedelta(days=12), "half", 5400)   # longer but easy: slower equivalent
    r = est(db)
    assert r.estimate_s == min(equiv(2400, 10.0, 42.195), equiv(5400, 21.0975, 42.195))
    assert r.estimate_s == equiv(2400, 10.0, 42.195) < equiv(5400, 21.0975, 42.195)
    assert [(s.band, s.sets_estimate) for s in r.sources] == [("10k", True), ("half", False)]


def test_excluded_best_effort_is_ignored(db):
    history(db)
    fast = effort(db, EVIDENCE_TO - timedelta(days=10), "10k", 2300)
    effort(db, EVIDENCE_TO - timedelta(days=11), "10k", 2500)
    fast.exclude_from_analysis = True
    db.commit()
    r = est(db)
    assert r.estimate_s == equiv(2500, 10.0, 42.195)
    assert fast.id not in [s.activity_id for s in r.sources]


def test_excluded_race_pb_is_ignored_though_race_pbs_keep_it(db):
    history(db)
    pb = past_race(db, EVIDENCE_TO - timedelta(days=10), km=10.0, result_s=2300)   # a 10k race result
    effort(db, EVIDENCE_TO - timedelta(days=11), "10k", 2500)
    assert est(db).estimate_s == equiv(2300, 10.0, 42.195)             # counts while unflagged
    db.get(Activity, pb.activity_id).exclude_from_analysis = True
    db.commit()
    r = est(db)
    assert r.estimate_s == equiv(2500, 10.0, 42.195)
    assert pb.activity_id not in [s.activity_id for s in r.sources]


def test_a_source_longer_than_the_race_is_not_used(db):
    history(db)
    effort(db, EVIDENCE_TO - timedelta(days=10), "half", 5000)
    r = est(db, km=21.0975)                    # same distance is allowed
    assert r.estimate_s == r.sources[0].equivalent_s and abs(r.estimate_s - 5000) <= 1   # ~no scaling
    effort(db, EVIDENCE_TO - timedelta(days=9), "full", 9000)
    assert "full" not in [s.band for s in est(db, km=21.0975).sources]


# --- history / range --------------------------------------------------------------------

def test_fewer_than_three_scored_races_gives_no_range(db):
    history(db, n=2, ten_k_s=(2400, 2450), actual_s=(5400, 5200))
    effort(db, EVIDENCE_TO - timedelta(days=10), "10k", 2400)
    r = est(db)
    assert r.state == "insufficient_history" and r.backtest_n == 2
    assert r.estimate_s == equiv(2400, 10.0, 42.195)
    assert r.low_s is None and r.high_s is None and r.band_pct is None and r.target_position is None
    assert r.message == "Only 2 past races to measure this method against (needs 3)."


def test_range_is_estimate_times_one_plus_minus_the_largest_past_error(db):
    days = history(db)
    effort(db, EVIDENCE_TO - timedelta(days=10), "10k", 2400)
    effort(db, EVIDENCE_TO - timedelta(days=12), "half", 5000)   # moderate: spreads to ≤ 10%
    r = est(db)
    assert r.state == "ok" and r.backtest_n == 3
    errs = [abs(round((equiv(t, 10.0, 21.0975) - a) / a, 4))
            for t, a in zip((2400, 2450, 2500), (5400, 5200, 5000))]
    assert [b.race_date for b in r.backtest] == [d.isoformat() for d in days]
    assert r.band_pct == r.backtest_max_abs_pct == max(errs) > 0
    assert r.grade != "thin"
    assert r.low_s == round(r.estimate_s * (1 - max(errs)))
    assert r.high_s == round(r.estimate_s * (1 + max(errs)))
    assert r.backtest_mean_abs_pct == round(sum(errs) / 3, 4)


def test_thin_evidence_widens_the_range_by_one_and_a_half(db):
    history(db)
    effort(db, EVIDENCE_TO - timedelta(days=10), "10k", 2400)
    effort(db, EVIDENCE_TO - timedelta(days=12), "half", 6500)   # equivalents disagree by > 10%
    r = est(db)
    assert r.grade == "thin" and r.state == "ok"
    assert r.low_s == round(r.estimate_s * (1 - r.band_pct * 1.5))
    assert r.high_s == round(r.estimate_s * (1 + r.band_pct * 1.5))
    assert r.band_pct == r.backtest_max_abs_pct          # band_pct itself is not widened


def test_target_position(db):
    history(db)
    effort(db, EVIDENCE_TO - timedelta(days=10), "10k", 2400)
    effort(db, EVIDENCE_TO - timedelta(days=12), "half", 5000)
    r = est(db)
    lo, hi = r.low_s, r.high_s
    assert est(db, target=lo - 1).target_position == "faster"
    assert est(db, target=lo).target_position == "inside"
    assert est(db, target=hi).target_position == "inside"
    assert est(db, target=hi + 1).target_position == "slower"
    assert est(db, target=None).target_position is None


# --- the backtest -----------------------------------------------------------------------

def test_dnf_past_race_is_skipped_with_a_reason_and_not_counted(db):
    history(db)
    past_race(db, date(2026, 8, 2), km=42.195, status="dnf", link_km=None, name="Dropped")
    r = est(db)
    assert r.backtest_n == 3
    assert [(s.name, s.reason) for s in r.backtest_skipped] == [("Dropped", "DNF — not a result")]


def test_linked_run_that_is_not_a_marathon_is_skipped(db):
    history(db)
    past_race(db, date(2026, 8, 2), km=42.195, result_s=3059, link_km=14.0, name="Beneva")
    r = est(db)
    assert r.backtest_n == 3
    assert [(s.name, s.reason) for s in r.backtest_skipped] == [("Beneva", "Linked run is 14.0 km, not a marathon")]


def test_other_skips_and_silent_ignores(db):
    history(db)
    past_race(db, date(2026, 5, 31), km=10.0, result_s=2400, name="A 10k")            # not half/marathon: ignored
    past_race(db, date(2026, 6, 14), km=17.0, result_s=4800, name="A 17k")            # ignored too
    past_race(db, date(2026, 7, 5), km=21.0975, status="planned", link_km=None, name="Stale plan")
    bad = past_race(db, date(2026, 7, 19), km=21.0975, result_s=5000, name="Flagged")
    db.get(Activity, bad.activity_id).exclude_from_analysis = True
    db.commit()
    past_race(db, date(2026, 7, 26), km=21.0975, result_s=1500, name="Too fast")      # 71 s/km
    r = est(db)
    assert r.backtest_n == 3
    assert {s.name: s.reason for s in r.backtest_skipped} == {
        "Stale plan": "Not completed, or no result time recorded",
        "Flagged": "Linked run is excluded from analysis",
        "Too fast": "Implausible pace (71 s/km)",
    }


def test_race_without_evidence_is_listed_but_not_counted(db):
    history(db)
    past_race(db, date(2026, 8, 2), result_s=5000, name="No build-up")
    r = est(db)
    row = next(b for b in r.backtest if b.name == "No build-up")
    assert row.predicted_s is None and row.error_s is None and row.error_pct is None
    assert r.backtest_n == 3 and len(r.backtest) == 4


def test_past_races_after_as_of_are_not_used(db):
    history(db)
    r = est(db, as_of=date(2026, 1, 5))        # only the first race (2026-01-04) is before this
    assert [b.race_date for b in r.backtest] == ["2026-01-04"]


def test_backtest_prediction_reproduces_from_as_of(db):
    history(db)
    r = est(db)
    for b in r.backtest:
        d = date.fromisoformat(b.race_date)
        again = fe.finish_estimate(db, race_distance_km=fe.NOMINAL_KM[b.race_class], target_time_s=None,
                                   as_of=d, evidence_to=d - timedelta(days=1))
        assert again.estimate_s == b.predicted_s
        assert b.error_s == b.predicted_s - b.actual_s


# --- the grade --------------------------------------------------------------------------

def grade(*sources, km=42.195):
    return fe._grade(list(sources), km)[0]


def test_grade_strong_boundaries():
    half = lambda age=30: src("half", 21.0975, age, 10000)   # 50% of a marathon
    assert grade(half(), src("10k", 10.0, 30, 10400)) == "strong"          # spread exactly 4%
    assert grade(half(), src("10k", 10.0, 30, 10401)) == "moderate"
    assert grade(half(42), src("10k", 10.0, 30, 10400)) == "strong"        # age exactly 42
    assert grade(half(43), src("10k", 10.0, 30, 10400)) == "moderate"
    assert grade(src("half", 18.0, 30, 10000), src("10k", 10.0, 30, 10400)) == "moderate"   # 43% reach
    assert grade(src("half", 19.0, 30, 10000), src("10k", 10.0, 30, 10400)) == "strong"     # 45%+ reach
    assert grade(half()) == "moderate"                                      # one distance can't be strong


def test_grade_thin_boundaries():
    half = src("half", 21.0975, 30, 10000)
    assert grade(half, src("10k", 10.0, 30, 11000)) == "moderate"          # spread exactly 10%: not thin
    assert grade(half, src("10k", 10.0, 30, 11001)) == "thin"
    assert grade(src("half", 21.0975, 56, 10000)) == "moderate"            # age exactly 56
    assert grade(src("half", 21.0975, 57, 10000)) == "thin"
    # an old 5k doesn't rescue/ruin it: only 10k+ ages count
    assert grade(src("half", 21.0975, 30, 10000), src("5k", 5.0, 200, 10100)) in ("moderate", "strong")


def test_grade_reasons_are_in_words():
    _, reasons, spread = fe._grade([src("half", 21.0975, 34, 10000), src("10k", 10.0, 34, 10260),
                                    src("5k", 5.0, 34, 10100)], 42.195)
    assert reasons[0] == "Longest source: half (21.1 km, 50% of the race), 34 days old"
    assert reasons[1] == "3 distances agree within 2.6%"
    _, reasons, _ = fe._grade([src("half", 21.0975, 34, 10000), src("10k", 10.0, 34, 11770)], 42.195)
    assert reasons[1] == "Sources disagree by 17.7% (more than 10%)"


def test_end_to_end_grade_and_spread(db):
    history(db)
    effort(db, EVIDENCE_TO - timedelta(days=10), "10k", 2400)
    effort(db, EVIDENCE_TO - timedelta(days=12), "half", 5000)
    r = est(db)
    eqs = [s.equivalent_s for s in r.sources]
    assert len(eqs) == 2
    assert r.spread_pct == round((max(eqs) - min(eqs)) / min(eqs), 4)
    assert r.grade_reasons and r.grade in ("strong", "moderate", "thin")


# --- COROS ------------------------------------------------------------------------------

def test_coros_prediction_comes_from_the_latest_snapshot_on_or_before_evidence_to(db):
    def snap(day, marathon_s):
        db.add(AthleteMetric(race_predictions={"42.195": marathon_s, "21.0975": marathon_s // 2},
                             captured_at=datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)))
    snap(EVIDENCE_TO - timedelta(days=30), 9900)
    snap(EVIDENCE_TO, 9000)                         # on the evidence date: counts
    snap(EVIDENCE_TO + timedelta(days=1), 8000)     # after: doesn't
    db.add(AthleteMetric(vo2max=60.0, captured_at=datetime(2026, 10, 9, 20, tzinfo=timezone.utc)))
    db.commit()
    r = est(db)
    assert r.coros_prediction_s == 9000 and r.coros_captured_at.startswith(EVIDENCE_TO.isoformat())
    assert est(db, km=21.0975).coros_prediction_s == 4500
    assert est(db, evidence_to=EVIDENCE_TO - timedelta(days=31)).coros_prediction_s is None
    assert est(db, km=10.0).coros_prediction_s is None


# --- the readiness payload ----------------------------------------------------------------

def test_readiness_carries_the_estimate(db):
    race(db)
    history(db)
    effort(db, EVIDENCE_TO - timedelta(days=10), "10k", 2400)
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.estimate.state in ("ok", "insufficient_history")
    assert rd.estimate.window_to == rd.block_end
    assert rd.estimate.target_time_s == 10800 and rd.estimate.race_class == "marathon"


def test_no_race_means_no_estimate(db):
    assert race_readiness(db, as_of=AS_OF).estimate is None


def test_readiness_estimate_over_rest_and_mcp(db, monkeypatch):
    race(db)
    history(db)
    effort(db, EVIDENCE_TO - timedelta(days=10), "10k", 2400)

    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)
    rest = get_race_readiness(as_of=AS_OF, db=db).model_dump()
    mcp = mcp_server.get_race_block_context(as_of=AS_OF.isoformat(), detail=True)["readiness"]
    assert rest["estimate"] == mcp["estimate"]
    assert rest["estimate"]["state"] == "ok" and rest["estimate"]["backtest_n"] == 3
    assert set(rest["estimate"]) >= {"state", "message", "estimate_s", "low_s", "high_s", "band_pct", "grade",
                                     "grade_reasons", "sources", "backtest", "backtest_skipped",
                                     "coros_prediction_s", "target_position", "heuristic"}
