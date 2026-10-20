"""R10.2 — race-block retrospective: `race_advisor.block_comparison`.

Rules under test: the block window shared with readiness (first Monday in, the
day before it out, the day before race day in, race day out); a finished
marathon block has 16 Monday-aligned weeks incl. zero-km ones; totals, peak
(tie -> later week), longest run, the 28.0 km long-run boundary; completed
races without a linked run, dnf, skipped, past-planned and future/in-progress
races; overlapping blocks; synthetic Race-tagged entries; class filtering and
ValueError; steady-run medians; and the read-only `races.race_entries` seam.
All tests pin `as_of`.
"""
from datetime import date, timedelta

import pytest

from app.models.models import Activity, PlannedRace
from app.services import races as races_svc
from app.services.race_advisor import block_comparison, block_window

AS_OF = date(2026, 10, 9)
RACE_DAY = date(2026, 3, 1)                       # Sunday; race Monday 2026-02-23
BLOCK_START = date(2025, 11, 10)                  # race Monday - 15 weeks


def run(db, day, km, *, tag=None, hr=None, moving_s=None, pace=None):
    a = Activity(source="manual", activity_type="Run", run_date=day, distance_km=km,
                 activity_tag=tag, avg_hr=hr, moving_time_s=moving_s, avg_pace_s_per_km=pace)
    db.add(a)
    db.commit()
    return a


def race(db, *, day=RACE_DAY, km=42.195, status="completed", name=" Spring Marathon ",
         result_s=None, target_s=None, activity_id=None):
    r = PlannedRace(name=name, race_date=day, distance_km=km, status=status,
                    result_time_s=result_s, target_time_s=target_s, activity_id=activity_id)
    db.add(r)
    db.commit()
    return r


def only_block(db, **kw):
    cmp = block_comparison(db, as_of=kw.pop("as_of", AS_OF), **kw)
    assert len(cmp.blocks) == 1
    return cmp.blocks[0]


# 1 --------------------------------------------------------------------------
def test_block_window_edges(db):
    assert block_window(RACE_DAY, 42.195)[2] == BLOCK_START
    race(db)
    run(db, BLOCK_START - timedelta(days=1), 10.0)     # day before block_start: out
    run(db, BLOCK_START, 11.0)                         # block_start: in
    run(db, RACE_DAY - timedelta(days=1), 12.0)        # day before race day: in
    run(db, RACE_DAY, 42.0)                            # race day: out
    b = only_block(db)
    assert b.runs == 2 and b.total_km == 23.0
    assert b.weeks[0].km == 11.0 and b.weeks[0].offset == -15
    assert b.weeks[-1].offset == 0 and b.weeks[-1].km == 12.0
    assert b.block_start == BLOCK_START.isoformat()
    assert b.block_end == (RACE_DAY - timedelta(days=1)).isoformat()


# 2 --------------------------------------------------------------------------
def test_finished_marathon_block_has_16_monday_weeks(db):
    race(db)
    run(db, BLOCK_START, 10.0)
    b = only_block(db)
    assert len(b.weeks) == 16
    assert [w.offset for w in b.weeks] == list(range(-15, 1))
    assert all(date.fromisoformat(w.week_start).weekday() == 0 for w in b.weeks)
    assert b.weeks[1].km == 0.0 and b.weeks[1].runs == 0 and b.weeks[1].longest_km == 0.0
    assert b.avg_week_km == round(10.0 / 16, 1)
    assert not b.in_progress


# 3 --------------------------------------------------------------------------
def test_totals_peak_longest_and_long_run_boundary(db):
    race(db)
    run(db, BLOCK_START + timedelta(days=1), 28.0)            # exactly the threshold: counts
    run(db, BLOCK_START + timedelta(days=8), 27.9)            # just under: doesn't
    run(db, BLOCK_START + timedelta(days=9), 0.1)
    b = only_block(db)
    assert b.long_run_km == 28.0 and b.long_runs == 1
    assert b.longest_run.distance_km == 28.0
    assert b.total_km == 56.0 and b.runs == 3
    assert b.peak_week.offset == -14 and b.peak_week.km == 28.0     # 28.0 vs 28.0 -> later wins
    assert b.peak_week.week_start == (BLOCK_START + timedelta(weeks=1)).isoformat()


def test_peak_week_tie_picks_later_week(db):
    race(db)
    run(db, BLOCK_START, 30.0)
    run(db, BLOCK_START + timedelta(weeks=3), 30.0)
    assert only_block(db).peak_week.offset == -12


def test_no_runs_means_no_peak_or_longest(db):
    race(db)
    b = only_block(db)
    assert b.peak_week is None and b.longest_run is None and b.total_km == 0.0
    assert b.steady_runs == 0 and b.median_m_per_beat is None


# 4 --------------------------------------------------------------------------
def test_completed_race_without_activity_gets_block_and_pace(db):
    race(db, result_s=12600, target_s=12000)
    b = only_block(db)
    assert b.race.name == "Spring Marathon" and b.race.activity_id is None
    assert b.race.result_pace == "4:59/km"  # 12600 s / 42.195 km = 298.6 s/km
    assert b.race.target_pace is not None and b.race.from_activity is False


# 5 --------------------------------------------------------------------------
def test_dnf_included_skipped_and_past_planned_excluded(db):
    race(db, status="dnf", name="DNF")
    race(db, status="skipped", name="Skip", day=RACE_DAY + timedelta(days=14))
    race(db, status="planned", name="Stale", day=RACE_DAY + timedelta(days=28))
    cmp = block_comparison(db, as_of=AS_OF)
    assert [b.race.name for b in cmp.blocks] == ["DNF"]
    assert cmp.blocks[0].race.status == "dnf" and cmp.blocks[0].race.result_time_s is None


def test_future_planned_race_is_in_progress_and_cut_at_as_of(db):
    day = date(2026, 11, 1)                                   # race Monday 2026-10-26
    race(db, day=day, status="planned")
    as_of = date(2026, 10, 14)                                # a Wednesday
    run(db, date(2026, 10, 13), 10.0)
    run(db, date(2026, 10, 14), 5.0)                          # as_of day itself is in
    run(db, date(2026, 10, 15), 99.0)                         # future: out
    b = only_block(db, as_of=as_of)
    assert b.in_progress and b.block_end == as_of.isoformat()
    assert b.total_km == 15.0
    assert b.weeks[-1].week_start == "2026-10-12" and b.weeks[-1].offset == -2
    assert len(b.weeks) == 14


def test_race_today_is_in_progress_with_block_ending_yesterday(db):
    race(db, day=AS_OF, status="planned")
    b = only_block(db)
    assert b.in_progress and b.block_end == (AS_OF - timedelta(days=1)).isoformat()


def test_block_not_started_has_empty_weeks(db):
    race(db, day=date(2027, 6, 6), status="planned")
    b = only_block(db)
    assert b.weeks == [] and b.total_km == 0.0 and b.runs == 0 and b.avg_week_km == 0.0
    assert b.peak_week is None and b.in_progress


# 6 --------------------------------------------------------------------------
def test_overlapping_blocks_share_runs(db):
    race(db, name="First")
    race(db, name="Second", day=RACE_DAY + timedelta(weeks=6))
    run(db, RACE_DAY - timedelta(days=10), 20.0)              # in both blocks
    cmp = block_comparison(db, as_of=AS_OF)
    assert [b.race.name for b in cmp.blocks] == ["First", "Second"]
    assert [b.total_km for b in cmp.blocks] == [20.0, 20.0]


# 7 --------------------------------------------------------------------------
def test_race_tagged_activity_without_plan_row_appears(db):
    a = run(db, RACE_DAY, 42.2, tag="Race", moving_s=12000)
    run(db, RACE_DAY - timedelta(days=7), 15.0)
    b = only_block(db)
    assert b.race.from_activity is True and b.race.id == -a.id and b.race.activity_id == a.id
    assert b.race.status == "completed" and b.total_km == 15.0


def test_class_filter_and_invalid_class(db):
    race(db, name="Marathon")
    race(db, name="Tenk", km=10.0, day=RACE_DAY + timedelta(days=14))
    race(db, name="Half", km=21.1, day=RACE_DAY + timedelta(days=28))
    assert [b.race.name for b in block_comparison(db, as_of=AS_OF).blocks] == ["Marathon"]
    half = block_comparison(db, race_class="half", as_of=AS_OF)
    assert [b.race.name for b in half.blocks] == ["Half"]
    assert half.block_weeks == 12 and half.long_run_km == 16.0
    with pytest.raises(ValueError, match="marathon"):
        block_comparison(db, race_class="ultra", as_of=AS_OF)


# 8 --------------------------------------------------------------------------
def test_steady_medians_exclude_tempo_but_count_in_totals(db):
    race(db)
    d = BLOCK_START + timedelta(days=1)
    run(db, d, 10.0, hr=150, moving_s=3000)                   # 300 s/km
    run(db, d + timedelta(days=1), 10.0, hr=160, moving_s=3200, tag="Easy")   # 320 s/km
    run(db, d + timedelta(days=2), 10.0, hr=180, moving_s=2500, tag="Tempo")
    b = only_block(db)
    assert b.total_km == 30.0 and b.runs == 3
    assert b.steady_runs == 2
    assert b.median_steady_pace_s_per_km == 310 and b.median_steady_hr == 155
    expect = sorted([10000 / (150 * 50.0), 10000 / (160 * 3200 / 60)])
    assert b.median_m_per_beat == round(sum(expect) / 2, 3)


# 9 --------------------------------------------------------------------------
def test_race_entries_does_not_prune_but_list_races_does(db):
    stale = race(db, status="planned", day=AS_OF - timedelta(days=30), name="Stale")
    sid = stale.id
    assert [r.id for r in races_svc.race_entries(db, AS_OF)] == [sid]
    assert db.query(PlannedRace).count() == 1
    block_comparison(db, as_of=AS_OF)
    assert db.query(PlannedRace).count() == 1
    assert races_svc.list_races(db, AS_OF) == []
    assert db.query(PlannedRace).count() == 0
