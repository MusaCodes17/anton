"""R8.4.4 — "am I ready for race X?": the readiness checklist in race_advisor.

Rules under test: no race ahead → has_race false and an empty checklist (the
roadmap's exit criterion — the card hides); which race is "next" (skipped
never, completed only before its date); the block's edges (its first Monday
counts, race-day running doesn't); the distance-relative long-run threshold at
its exact boundary (28.0 km counts for a marathon, 27.9 doesn't); 3 long runs
needed; longest run at exactly the target; the key effort vs. target pace
(at-or-faster is met, slower is not_met, none recorded is no_data, no target is n/a); the
8-week effort window; n/a before the block starts and for a race with no
distance; read-only (no prune); REST and MCP agree. All tests pin `as_of`.
"""
from contextlib import contextmanager
from datetime import date, timedelta

from app import mcp_server
from app.models.models import Activity, ActivityBestEffort, ActivitySplit, ActivityEffortScan, OwnedShoe, PlannedRace
from app.routers.races import get_race_readiness
from app.services import rotation
from app.services.race_advisor import _consistency, _taper, race_block_context, race_readiness
from types import SimpleNamespace

AS_OF = date(2026, 10, 9)              # a Friday
RACE_DAY = date(2026, 10, 11)          # Sunday; race week starts Mon 2026-10-05
BLOCK_START = date(2026, 6, 22)        # 16-week marathon block: race Monday − 15 weeks


def run(db, day, km, *, elapsed_s=None):
    a = Activity(source="manual", activity_type="Run", run_date=day, distance_km=km,
                 elapsed_time_s=elapsed_s)
    db.add(a)
    db.commit()
    return a


def race(db, *, day=RACE_DAY, km=42.195, target_s=10800, status="planned", name="Beneva Marathon"):
    r = PlannedRace(name=name, race_date=day, distance_km=km, target_time_s=target_s, status=status)
    db.add(r)
    db.commit()
    return r


def effort(db, day, label, elapsed_s, run_km=25.0):
    """A scanned run with one best-effort segment (R8.2)."""
    a = run(db, day, run_km, elapsed_s=int(run_km * 300))
    db.add(ActivityEffortScan(activity_id=a.id, status="ok", source="fit"))
    db.add(ActivityBestEffort(activity_id=a.id, distance_label=label, elapsed_s=elapsed_s,
                              start_offset_m=0, source="fit"))
    db.commit()
    return a


def splits(db, activity, moving, *, last_partial_m=None):
    """Real ActivitySplit rows: one 1000 m split per moving_s entry (elapsed = moving),
    plus an optional trailing partial of `last_partial_m` metres (60 s)."""
    for i, m in enumerate(moving, start=1):
        db.add(ActivitySplit(activity_id=activity.id, split_index=i, distance_m=1000,
                             elapsed_s=m, moving_s=m, source="fit"))
    if last_partial_m:
        db.add(ActivitySplit(activity_id=activity.id, split_index=len(moving) + 1,
                             distance_m=last_partial_m, elapsed_s=60, moving_s=60, source="fit"))
    db.commit()


def items(rd):
    return {i.key: i for i in rd.checklist}


# --- no race → hides ---------------------------------------------------------------------

def test_no_race_means_no_readiness(db):
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.has_race is False
    assert rd.race is None and rd.checklist == [] and rd.long_runs == []


def test_past_and_skipped_races_are_not_next(db):
    race(db, day=AS_OF - timedelta(days=1), name="Yesterday")
    race(db, status="skipped", name="Skipped")
    assert race_readiness(db, as_of=AS_OF).has_race is False


def test_completed_race_counts_only_before_its_date(db):
    race(db, status="completed")
    assert race_readiness(db, as_of=RACE_DAY - timedelta(days=1)).race.name == "Beneva Marathon"
    assert race_readiness(db, as_of=RACE_DAY).has_race is False


def test_planned_race_today_is_next(db):
    race(db)
    rd = race_readiness(db, as_of=RACE_DAY)
    assert rd.race.days_to_race == 0 and rd.race.weeks_to_race == 0


def test_soonest_race_wins(db):
    race(db)
    race(db, day=AS_OF + timedelta(days=1), km=5.0, target_s=1200, name="Parkrun")
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.race.name == "Parkrun" and rd.race_class == "5k"


def test_readiness_does_not_prune_stale_plans(db):
    stale = race(db, day=AS_OF - timedelta(days=30), name="Stale")
    race(db)
    race_readiness(db, as_of=AS_OF)
    assert db.query(PlannedRace).filter(PlannedRace.id == stale.id).first() is not None


# --- the block -----------------------------------------------------------------------------

def test_block_edges(db):
    race(db)
    run(db, BLOCK_START - timedelta(days=1), 30)   # Sunday before the block: out
    run(db, BLOCK_START, 30)                       # the block's first Monday: in
    run(db, RACE_DAY, 42.2)                        # race day: never part of the block
    rd = race_readiness(db, as_of=RACE_DAY)
    assert rd.block_start == "2026-06-22" and rd.block_end == "2026-10-10" and rd.block_weeks == 16
    assert rd.block_runs == 1 and rd.block_km == 30.0
    assert [r.run_date for r in rd.long_runs] == ["2026-06-22"]


def test_weeks_to_go_and_peak_week(db):
    race(db)
    run(db, date(2026, 9, 14), 40)                 # 2026-W38
    run(db, date(2026, 9, 16), 50)                 # 2026-W38 → 90 km, the peak
    run(db, date(2026, 9, 22), 60)                 # 2026-W39
    run(db, date(2026, 10, 6), 12)                 # 2026-W41, this week
    rd = race_readiness(db, as_of=AS_OF)
    it = items(rd)
    assert it["weeks_to_go"].value == 0 and it["weeks_to_go"].status == "info"   # 2 days → 0 weeks
    assert rd.peak_week.period == "2026-W38" and rd.peak_week.total_km == 90.0
    assert it["peak_week"].value == 90.0 and it["peak_week"].status == "info"
    assert rd.current_week.period == "2026-W41" and rd.current_week.total_km == 12.0


def test_long_run_threshold_boundary_and_count(db):
    race(db)
    run(db, date(2026, 8, 2), 28.0)                # exactly the marathon threshold: counts
    run(db, date(2026, 8, 9), 27.9)                # just under: doesn't
    run(db, date(2026, 8, 16), 30.0)
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.long_run_km == 28.0
    assert [r.distance_km for r in rd.long_runs] == [28.0, 30.0]
    lr = items(rd)["long_runs"]
    assert (lr.value, lr.target, lr.status) == (2, 3, "not_met")

    run(db, date(2026, 8, 23), 29.0)
    assert items(race_readiness(db, as_of=AS_OF))["long_runs"].status == "met"


def test_longest_run_met_at_exactly_the_target(db):
    race(db)
    run(db, date(2026, 9, 6), 31.9)
    assert items(race_readiness(db, as_of=AS_OF))["longest_run"].status == "not_met"
    run(db, date(2026, 9, 13), 32.0)
    lr = items(race_readiness(db, as_of=AS_OF))["longest_run"]
    assert (lr.value, lr.target, lr.status) == (32.0, 32.0, "met")


def test_thresholds_scale_with_race_distance(db):
    race(db, km=21.1, target_s=4800, name="Half")
    run(db, AS_OF - timedelta(days=3), 16.0)
    run(db, AS_OF - timedelta(days=10), 15.9)
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.race_class == "half" and rd.block_weeks == 12 and rd.long_run_km == 16.0
    assert [r.distance_km for r in rd.long_runs] == [16.0]
    assert items(rd)["long_runs"].label == "Long runs ≥ 16 km"


def test_block_not_started_is_not_applicable(db):
    race(db)
    rd = race_readiness(db, as_of=BLOCK_START - timedelta(days=1))
    assert rd.block_started is False
    it = items(rd)
    for key in ("peak_week", "longest_run", "long_runs"):
        assert it[key].status == "n/a" and "block starts 2026-06-22" in it[key].rule


def test_race_without_distance_has_no_distance_rules(db):
    race(db, km=None, target_s=None, name="Mystery race")
    run(db, AS_OF - timedelta(days=2), 30)
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.race_class is None and rd.block_weeks == 12
    it = items(rd)
    assert it["peak_week"].status == "info"
    assert {it[k].status for k in ("longest_run", "long_runs", "key_effort")} == {"n/a"}


# --- recent efforts vs. target pace -----------------------------------------------------------

def test_key_effort_at_target_pace_is_met(db):
    race(db)                                       # 3:00:00 → 4:16/km (256 s/km)
    effort(db, AS_OF - timedelta(days=20), "half", round(256 * 21.0975))
    rd = race_readiness(db, as_of=AS_OF)
    e = next(e for e in rd.recent_efforts if e.label == "half")
    assert e.vs_target_s_per_km == 0 and e.segment is True
    ke = items(rd)["key_effort"]
    assert ke.status == "met" and ke.value == ke.target == 256 and ke.unit == "s/km"


def test_key_effort_slower_than_target_is_not_met(db):
    race(db)
    effort(db, AS_OF - timedelta(days=20), "half", 21 * 60 * 4 + 1800)   # ~5:00/km
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.recent_efforts[0].vs_target_s_per_km > 0
    assert items(rd)["key_effort"].status == "not_met"


def test_no_recent_key_effort_is_no_data_and_old_efforts_drop_out(db):
    race(db)
    effort(db, AS_OF - timedelta(weeks=8), "half", 4800)            # one day outside the window
    effort(db, AS_OF - timedelta(days=10), "10k", 2400)             # inside, but not the key distance
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.effort_window_start == "2026-08-15"
    assert [e.label for e in rd.recent_efforts] == ["10k"]
    ke = items(rd)["key_effort"]
    assert ke.status == "no_data" and ke.value is None and ke.evidence == [] and ke.age_days is None
    assert "No half effort recorded since 2026-08-15" in ke.rule


def test_no_target_lists_efforts_without_a_comparison(db):
    race(db, target_s=None)
    effort(db, AS_OF - timedelta(days=20), "half", 5000)
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.recent_efforts[0].vs_target_s_per_km is None
    ke = items(rd)["key_effort"]
    assert ke.status == "n/a" and "No target time" in ke.rule


# --- R11.1: evidence, periods, no_data ---------------------------------------------------------

def test_started_block_with_no_runs_is_no_data_not_not_met(db):
    race(db)
    it = items(race_readiness(db, as_of=AS_OF))
    for key in ("peak_week", "longest_run", "long_runs"):
        assert it[key].status == "no_data" and it[key].evidence == []
        assert (it[key].period_from, it[key].period_to) == ("2026-06-22", "2026-10-09")
    assert it["longest_run"].rule == "No runs in the block yet"
    assert it["peak_week"].rule == "No running in the block yet"


def test_runs_but_none_long_is_not_met_with_empty_evidence(db):
    race(db)
    run(db, date(2026, 9, 6), 10)
    it = items(race_readiness(db, as_of=AS_OF))
    assert it["long_runs"].status == "not_met" and it["long_runs"].evidence == []
    assert it["longest_run"].status == "not_met" and len(it["longest_run"].evidence) == 1


def test_evidence_matches_the_numbers_and_periods(db):
    race(db)
    a = run(db, date(2026, 9, 14), 40)              # 2026-W38, the peak
    b = run(db, date(2026, 9, 16), 50)
    c = run(db, date(2026, 9, 22), 29.0)            # W39: a long run
    d = run(db, date(2026, 10, 1), 30.0)            # W40: a long run
    k = effort(db, AS_OF - timedelta(days=20), "half", round(256 * 21.0975))
    rd = race_readiness(db, as_of=AS_OF)
    it = items(rd)
    assert it["weeks_to_go"].evidence == [] and it["weeks_to_go"].period_from is None

    assert [e.activity_id for e in it["peak_week"].evidence] == [a.id, b.id, k.id]   # oldest first; the effort run (Sep 19) is in W38 too
    assert it["peak_week"].evidence[0].run_date == "2026-09-14"
    assert round(sum(e.distance_km for e in it["peak_week"].evidence), 1) == rd.peak_week.total_km

    assert [e.activity_id for e in it["longest_run"].evidence] == [rd.longest_run.activity_id]
    assert [e.activity_id for e in it["long_runs"].evidence] == [r.activity_id for r in rd.long_runs]
    assert d.id in [e.activity_id for e in it["long_runs"].evidence]

    for key in ("peak_week", "longest_run", "long_runs"):
        assert (it[key].period_from, it[key].period_to) == (rd.block_start, rd.block_end)

    ke = it["key_effort"]
    assert (ke.period_from, ke.period_to) == (rd.effort_window_start, rd.block_end)
    assert [e.activity_id for e in ke.evidence] == [k.id]
    assert ke.evidence[0].segment is True and ke.evidence[0].distance_km == 21.1
    assert ke.age_days == 20


def test_key_effort_without_target_still_carries_evidence(db):
    race(db, target_s=None)
    k = effort(db, AS_OF - timedelta(days=20), "half", 5000)
    ke = items(race_readiness(db, as_of=AS_OF))["key_effort"]
    assert ke.status == "n/a" and ke.age_days == 20 and [e.activity_id for e in ke.evidence] == [k.id]
    assert ke.period_from == "2026-08-15"


def test_no_data_is_a_known_status():
    from app.services.race_advisor import STATUSES
    assert "no_data" in STATUSES


# --- surfaces ---------------------------------------------------------------------------------

def test_race_block_context_carries_readiness(db):
    race(db)
    ctx = race_block_context(db, today=AS_OF)
    assert ctx.readiness.has_race and ctx.readiness.race.name == ctx.next_race.name


def test_endpoint_and_mcp_tool_agree(db, monkeypatch):
    race(db)
    lr = run(db, date(2026, 9, 13), 32.0)
    splits(db, lr, [300, 300, 290, 290])
    effort(db, AS_OF - timedelta(days=20), "half", 5300)

    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)

    rest = get_race_readiness(as_of=AS_OF, db=db).model_dump()
    mcp = mcp_server.get_race_block_context(as_of=AS_OF.isoformat())["readiness"]
    assert rest == mcp
    assert rest["has_race"] is True and rest["heuristic"] is True
    assert rest["estimate"] is not None and rest["estimate"] == mcp["estimate"]   # R11.7 rides the payload
    assert [i["key"] for i in rest["checklist"]] == [
        "weeks_to_go", "peak_week", "longest_run", "long_runs", "key_effort", "race_shoe",
        "weeks_with_running", "gaps", "taper_volume", "since_long_run",   # R11.3 appends the info items
        "fast_finish"]                                                    # R11.6
    assert len(rest["long_run_finishes"]) == 1 and rest["long_run_finishes"] == mcp["long_run_finishes"]
    assert rest["long_run_finishes"][0]["split_diff_s_per_km"] == -10


def test_endpoint_without_a_race_says_so(db):
    assert get_race_readiness(as_of=AS_OF, db=db).model_dump()["has_race"] is False


def test_mcp_tool_rejects_a_bad_date():
    assert "error" in mcp_server.get_race_block_context(as_of="next sunday")


# --- R11.2 — "at this point in past builds" ------------------------------------------------
# Readiness AS_OF is 2 days before RACE_DAY, so every past block is cut at race_date − 2.

PAST_DAY = date(2026, 3, 8)            # a Sunday; cut = Fri 2026-03-06


def test_past_build_counts_only_runs_up_to_the_cut(db):
    race(db)
    race(db, day=PAST_DAY, status="completed", name="Spring Marathon")
    run(db, date(2026, 2, 1), 20.0)
    run(db, date(2026, 2, 8), 30.0)        # long
    run(db, date(2026, 3, 6), 10.0)        # exactly on the cut: counts
    run(db, date(2026, 3, 7), 35.0)        # after the cut: doesn't
    run(db, PAST_DAY, 42.2)                # race day: never
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.days_before_race == 2
    [pb] = rd.past_builds
    assert pb.cut_date == "2026-03-06"
    assert (pb.km, pb.runs, pb.long_runs) == (60.0, 3, 1)
    assert pb.longest_km == 30.0
    assert pb.peak_week_km == 30.0       


def test_past_build_with_no_runs_before_the_cut_is_zeros_but_listed(db):
    race(db)
    race(db, day=PAST_DAY, status="completed")
    run(db, date(2026, 3, 7), 35.0)        # only after the cut
    [pb] = race_readiness(db, as_of=AS_OF).past_builds
    assert (pb.km, pb.runs, pb.long_runs) == (0.0, 0, 0)
    assert pb.longest_km is None and pb.peak_week_km is None


def test_dnf_past_race_is_included_without_a_result_delta(db):
    race(db)
    race(db, day=PAST_DAY, status="dnf", name="Bad Day")
    [pb] = race_readiness(db, as_of=AS_OF).past_builds
    assert pb.race.status == "dnf" and pb.result_vs_target_s is None


def test_result_vs_target_is_negative_when_faster(db):
    race(db)
    r = race(db, day=PAST_DAY, status="completed", target_s=10800)
    r.result_time_s = 10500
    db.commit()
    [pb] = race_readiness(db, as_of=AS_OF).past_builds
    assert pb.result_vs_target_s == -300


def test_past_builds_same_class_only_newest_first(db):
    race(db)
    race(db, day=date(2026, 3, 8), status="completed", name="Older")
    race(db, day=date(2026, 5, 3), status="completed", name="Newer")
    race(db, day=date(2026, 4, 5), km=10.0, status="completed", name="Ten K")   # other class
    race(db, day=date(2026, 6, 7), status="skipped", name="Skipped")
    assert [b.race.name for b in race_readiness(db, as_of=AS_OF).past_builds] == ["Newer", "Older"]


def test_no_past_races_or_block_not_started_means_empty(db):
    race(db)
    assert race_readiness(db, as_of=AS_OF).past_builds == []
    race(db, day=PAST_DAY, status="completed")
    assert race_readiness(db, as_of=BLOCK_START - timedelta(days=1)).past_builds == []
    assert race_readiness(db, as_of=BLOCK_START - timedelta(days=1)).days_before_race is None


# --- R11.3 — consistency + taper -----------------------------------------------------------

D = date
MON = date(2026, 6, 22)                # a Monday


def days(*offsets):
    return [MON + timedelta(days=o) for o in offsets]


def test_gap_spanning_a_week_boundary_is_one_gap(db):
    # Fri 06-26 → Sun 07-05: eight days off across a Monday boundary.
    runs = days(0, 1, 2, 3, 4) + days(13) + days(14, 15, 16, 17, 18, 19, 20)
    c = _consistency(runs, MON, MON + timedelta(days=20))
    assert [(g.start, g.end, g.days) for g in c.gaps] == [("2026-06-27", "2026-07-04", 8)]


def test_exactly_seven_days_off_counts_six_does_not():
    base = days(0, 1, 2, 3, 4)                       # ... Fri 06-26
    seven = _consistency(base + days(12, 13, 14), MON, MON + timedelta(days=14))   # next run Sat 07-04
    six = _consistency(base + days(11, 12, 13, 14), MON, MON + timedelta(days=14))  # next run Fri 07-03
    assert [g.days for g in seven.gaps] == [7]
    assert six.gaps == []


def test_leading_and_trailing_gaps_count():
    # Block starts Mon 06-22, first run Wed 07-01 (9 days off); last run Fri 07-03, block ends Sun 07-12 (9 off, 07-04 → 07-12).
    c = _consistency(days(9, 11), MON, MON + timedelta(days=20))
    assert [(g.start, g.end, g.days) for g in c.gaps] == [
        ("2026-06-22", "2026-06-30", 9), ("2026-07-04", "2026-07-12", 9)]
    assert _consistency([], MON, MON + timedelta(days=9)).gaps[0].days == 10   # no runs: the whole block


def test_one_week_block_and_partial_week_count():
    c = _consistency(days(0, 2, 3), MON, MON + timedelta(days=3))   # block ended Thursday
    assert (c.weeks_elapsed, c.weeks_with_runs, c.median_runs_per_week) == (1, 1, 3.0)
    assert c.gaps == []


def test_multi_week_block_with_a_zero_week_counts_the_zero_in_the_median():
    # weeks: 3 runs, 0 runs, 2 runs, 1 run → median of [3,0,2,1] = 1.5
    runs = days(0, 1, 2) + days(14, 16) + days(21)
    c = _consistency(runs, MON, MON + timedelta(days=27))
    assert (c.weeks_elapsed, c.weeks_with_runs, c.median_runs_per_week) == (4, 3, 1.5)


def _taper_race(db):
    race(db)                                          # Sunday 2026-10-11, marathon
    run(db, date(2026, 9, 15), 40.0)                  # peak week, and a long run
    run(db, date(2026, 9, 22), 20.0)                  # week -2
    run(db, date(2026, 9, 29), 10.0)                  # week -1
    run(db, date(2026, 10, 6), 4.0)                   # race week so far


def test_taper_hidden_at_22_days_shown_at_21(db):
    _taper_race(db)
    far = race_readiness(db, as_of=RACE_DAY - timedelta(days=22))
    assert far.taper is None
    assert not {"taper_volume", "since_long_run"} & set(items(far))
    near = race_readiness(db, as_of=RACE_DAY - timedelta(days=21))
    assert near.taper is not None
    assert {"taper_volume", "since_long_run"} <= set(items(near))


def test_taper_percentages_complete_flag_and_long_run_age(db):
    _taper_race(db)
    rd = race_readiness(db, as_of=AS_OF)              # Fri 10-09
    t = rd.taper
    assert t.peak_week_km == 40.0
    assert [(w.offset, w.km, w.pct_of_peak, w.complete) for w in t.weeks] == [
        (-2, 20.0, 50, True), (-1, 10.0, 25, True), (0, 4.0, 10, False)]
    assert t.days_since_long_run == 24                # 09-15 → block_end 10-09
    assert t.days_since_key_effort is None
    its = items(rd)
    assert its["taper_volume"].value == 25 and its["taper_volume"].status == "info"
    assert its["taper_volume"].target is None
    assert "race week so far: 10%" in its["taper_volume"].rule
    assert its["since_long_run"].value == 24 and its["since_long_run"].evidence[0].distance_km == 40.0


def test_taper_week_not_yet_started_is_listed_with_zero_km():
    runs = [SimpleNamespace(date=date(2026, 9, 15), distance_km=40.0)]
    t = _taper(runs, RACE_DAY, BLOCK_START, date(2026, 9, 20), 40.0, date(2026, 9, 20))
    assert [(w.offset, w.km, w.complete) for w in t.weeks] == [(-2, 0.0, False), (-1, 0.0, False), (0, 0.0, False)]
    assert _taper(runs, RACE_DAY, BLOCK_START, date(2026, 9, 20), None, date(2026, 9, 20)).weeks[0].pct_of_peak is None


def test_consistency_items_are_info_only_and_omitted_before_the_block(db):
    race(db)
    run(db, date(2026, 10, 1), 10.0)
    rd = race_readiness(db, as_of=AS_OF)
    its = items(rd)
    assert its["weeks_with_running"].status == "info" and its["gaps"].status == "info"
    assert its["weeks_with_running"].rule.startswith(f"1 of {rd.consistency.weeks_elapsed} weeks had a run")
    assert its["gaps"].value == 2                      # block start → first run, and the ongoing stretch after it
    assert "→" in its["gaps"].rule
    early = race_readiness(db, as_of=BLOCK_START - timedelta(days=1))
    assert early.consistency is None
    assert not {"weeks_with_running", "gaps"} & set(items(early))


def test_past_build_carries_consistency_and_taper_at_its_cut(db):
    race(db)
    race(db, day=PAST_DAY, status="completed", name="Spring Marathon")
    run(db, date(2026, 2, 10), 40.0)
    run(db, date(2026, 3, 3), 20.0)                    # Tuesday of that race week, before the cut
    rd = race_readiness(db, as_of=AS_OF)
    [pb] = rd.past_builds
    assert pb.consistency.weeks_with_runs == 2
    assert pb.taper is not None and pb.taper.peak_week_km == 40.0
    assert [(w.offset, w.pct_of_peak) for w in pb.taper.weeks] == [(-2, 0), (-1, 0), (0, 50)]
    assert rd.taper is not None
    far = race_readiness(db, as_of=RACE_DAY - timedelta(days=22))
    assert far.taper is None and far.past_builds[0].taper is None
    assert far.past_builds[0].consistency is not None


# --- R11.5 — the race shoe: projected race-day km vs its own limit, and block usage ---------
# The race is 21 days after AS_OF, so the projection is today's ledger + 3 weeks of the
# shoe's recent rate. Its only attributed run (60 km on Sep 20) sits in the 6-week window,
# so the recent rate is 60 / 6 = 10 km/week and the projection is 60 + 10 × 21 / 7 = 90 km.

SHOE_RACE_DAY = AS_OF + timedelta(days=21)     # Fri 2026-10-30


def _shoe(db, *, limit=None, nickname=None, brand="Adios", model="Pro"):
    s = OwnedShoe(brand=brand, model=model, nickname=nickname, starting_mileage=0,
                  current_mileage=0, mileage_limit=limit)
    db.add(s)
    db.commit()
    return s


def _attr(db, shoe, day, km):
    return rotation.log_run(db, shoe.id, distance_km=km, run_date=day).activity


def _race_with_shoe(db, shoe=None, *, day=SHOE_RACE_DAY, km=42.195):
    r = race(db, day=day, km=km)
    r.planned_shoe_id = shoe.id if shoe else None
    db.commit()
    return r


def _race_shoe_item(db):
    return items(race_readiness(db, as_of=AS_OF))["race_shoe"]


def test_race_shoe_projection_under_limit_is_met(db):
    shoe = _shoe(db, limit=95)
    _attr(db, shoe, date(2026, 9, 20), 60.0)
    _race_with_shoe(db, shoe)
    it = _race_shoe_item(db)
    assert it.key == "race_shoe" and it.label == "Race shoe · Adios Pro" and it.unit == "km"
    assert (it.value, it.target, it.status) == (90.0, 95.0, "met")
    assert "Projected 90 km on race day, within its 95 km limit" in it.rule


def test_race_shoe_projection_over_limit_is_not_met(db):
    shoe = _shoe(db, limit=85)
    _attr(db, shoe, date(2026, 9, 20), 60.0)
    _race_with_shoe(db, shoe)
    it = _race_shoe_item(db)
    assert (it.value, it.target, it.status) == (90.0, 85.0, "not_met")
    assert "Projected 90 km on race day passes its 85 km limit" in it.rule


def test_race_shoe_projection_exactly_at_limit_is_met(db):
    shoe = _shoe(db, limit=90)
    _attr(db, shoe, date(2026, 9, 20), 60.0)
    _race_with_shoe(db, shoe)
    it = _race_shoe_item(db)
    assert (it.value, it.target, it.status) == (90.0, 90.0, "met")


def test_no_race_shoe_is_n_a(db):
    _race_with_shoe(db, None)
    it = _race_shoe_item(db)
    assert it.status == "n/a" and it.value is None and it.target is None
    assert it.rule == "No race shoe picked — choose one on the race"
    assert race_readiness(db, as_of=AS_OF).race_shoe is None


def test_deleted_race_shoe_is_nulled_and_n_a(db):
    shoe = _shoe(db, limit=100)
    r = _race_with_shoe(db, shoe)
    rotation.delete_owned_shoe(db, shoe.id)
    db.refresh(r)
    assert r.planned_shoe_id is None
    assert _race_shoe_item(db).status == "n/a"


def test_race_shoe_without_limit_is_info(db):
    shoe = _shoe(db, limit=None, nickname="Race day Adios")
    _attr(db, shoe, date(2026, 9, 20), 60.0)
    _race_with_shoe(db, shoe)
    rs = race_readiness(db, as_of=AS_OF).race_shoe
    it = _race_shoe_item(db)
    assert rs.label == "Race day Adios" and rs.mileage_limit is None
    assert (it.status, it.value, it.target) == ("info", 90.0, None)
    assert "no mileage limit set" in it.rule


def test_race_shoe_block_usage_and_evidence_count_only_this_shoes_block_runs(db):
    shoe = _shoe(db, limit=200)
    other = _shoe(db, limit=200, brand="Saucony", model="Endorphin")
    before = _attr(db, shoe, date(2026, 7, 1), 15.0)       # before the block (starts Jul 13): out
    early = _attr(db, shoe, date(2026, 9, 20), 60.0)       # in the block, this shoe
    late = _attr(db, shoe, date(2026, 9, 25), 10.0)        # in the block, this shoe
    _attr(db, other, date(2026, 9, 22), 30.0)              # in the block, another shoe: out
    _race_with_shoe(db, shoe)

    rd = race_readiness(db, as_of=AS_OF)
    rs = rd.race_shoe
    assert (rs.block_runs, rs.block_km, rs.longest_km, rs.last_run_date) == (2, 70.0, 60.0, "2026-09-25")
    it = items(rd)["race_shoe"]
    assert [e.activity_id for e in it.evidence] == [early.id, late.id]   # oldest first
    assert before.id not in [e.activity_id for e in it.evidence]
    assert (it.period_from, it.period_to) == (rd.block_start, rd.block_end)
    assert it.rule.endswith("; in the block: 2 runs, 70 km, last 2026-09-25")


def test_race_shoe_before_block_starts_has_no_usage(db):
    shoe = _shoe(db, limit=200)
    _attr(db, shoe, date(2026, 9, 20), 60.0)
    _race_with_shoe(db, shoe, day=AS_OF + timedelta(days=200), km=None)   # block starts after as_of
    rs = race_readiness(db, as_of=AS_OF).race_shoe
    it = items(race_readiness(db, as_of=AS_OF))["race_shoe"]
    assert (rs.block_runs, rs.block_km, rs.longest_km, rs.last_run_date) == (0, 0.0, None, None)
    assert it.evidence == [] and it.period_from is None and "in the block" not in it.rule


def test_race_shoe_label_names_the_shoe(db):
    named = _shoe(db, limit=200, nickname="Race day Adios")
    _race_with_shoe(db, named)
    assert _race_shoe_item(db).label == "Race shoe · Race day Adios"


def test_race_shoe_label_falls_back_to_brand_and_model(db):
    plain = _shoe(db, limit=200, brand="Saucony", model="Endorphin Speed")
    _race_with_shoe(db, plain)
    assert _race_shoe_item(db).label == "Race shoe · Saucony Endorphin Speed"


def test_race_shoe_label_is_plain_when_no_shoe(db):
    _race_with_shoe(db, None)
    assert _race_shoe_item(db).label == "Race shoe"


# --- R11.6 long-run finishes ---------------------------------------------------------------

LONG_DAY = date(2026, 9, 13)


def finishes(db):
    rd = race_readiness(db, as_of=AS_OF)
    return rd, items(rd)["fast_finish"]


def test_negative_positive_and_equal_splits_count_only_when_faster(db):
    race(db)
    neg = run(db, LONG_DAY, 32.0)
    splits(db, neg, [310, 310, 290, 290])
    pos = run(db, LONG_DAY + timedelta(days=1), 32.0)
    splits(db, pos, [290, 290, 310, 310])
    eq = run(db, LONG_DAY + timedelta(days=2), 32.0)
    splits(db, eq, [300, 300, 300, 300])
    rd, it = finishes(db)
    assert [f.split_diff_s_per_km for f in rd.long_run_finishes] == [-20, 20, 0]
    assert it.status == "info" and it.value == 1 and it.unit == "runs" and it.target is None
    assert it.rule == "1 of 3 long runs had a faster second half (moving pace)"
    assert [e.activity_id for e in it.evidence] == [neg.id, pos.id, eq.id]


def test_odd_split_count_with_trailing_partial_halves(db):
    race(db)
    a = run(db, LONG_DAY, 32.0)
    # 5 full km + a 500 m partial of 60 s (= 120 s/km): k = 6 // 2 = 3
    splits(db, a, [300, 300, 300, 270, 270], last_partial_m=500)
    [f] = race_readiness(db, as_of=AS_OF).long_run_finishes
    assert f.first_half_pace_s_per_km == 300
    assert f.second_half_pace_s_per_km == round((270 + 270 + 60) / 2.5)   # 240
    assert f.moving_pace_s_per_km == round((1440 + 60) / 5.5)             # 273
    assert f.split_diff_s_per_km == 240 - 300


def test_last_km_is_the_last_full_split_not_the_partial(db):
    race(db)
    a = run(db, LONG_DAY, 32.0)
    splits(db, a, [300, 300, 280, 260], last_partial_m=200)
    [f] = race_readiness(db, as_of=AS_OF).long_run_finishes
    assert f.last_km_pace_s_per_km == 260
    assert f.last_km_vs_avg_s_per_km == 260 - f.moving_pace_s_per_km


def test_second_half_vs_target_needs_a_target(db):
    race(db, target_s=10800)   # 10800 / 42.195 = 255.95 -> 256 s/km
    a = run(db, LONG_DAY, 32.0)
    splits(db, a, [300, 300, 280, 280])
    [f] = race_readiness(db, as_of=AS_OF).long_run_finishes
    assert f.second_half_vs_target_s_per_km == 280 - 256


def test_no_target_leaves_vs_target_none(db):
    race(db, target_s=None)
    a = run(db, LONG_DAY, 32.0)
    splits(db, a, [300, 300, 280, 280])
    [f] = race_readiness(db, as_of=AS_OF).long_run_finishes
    assert f.has_splits and f.second_half_vs_target_s_per_km is None


def test_unscanned_long_run_is_listed_and_counted_as_missing(db):
    race(db)
    a = run(db, LONG_DAY, 32.0)
    splits(db, a, [310, 310, 290, 290])
    bare = run(db, LONG_DAY + timedelta(days=1), 32.0)
    rd, it = finishes(db)
    f = rd.long_run_finishes[1]
    assert f.activity_id == bare.id and f.has_splits is False
    assert f.split_diff_s_per_km is None and f.moving_pace_s_per_km is None
    assert it.rule == "1 of 1 long runs had a faster second half (moving pace); 1 not scanned yet"
    assert [e.activity_id for e in it.evidence] == [a.id]


def test_single_split_counts_as_no_splits(db):
    race(db)
    a = run(db, LONG_DAY, 32.0)
    splits(db, a, [300])
    [f] = race_readiness(db, as_of=AS_OF).long_run_finishes
    assert f.has_splits is False


def test_all_unscanned_is_no_data(db):
    race(db)
    run(db, LONG_DAY, 32.0)
    rd, it = finishes(db)
    assert it.status == "no_data" and it.value is None
    assert it.rule == "No long run in the block has per-km splits yet (runs are scanned after they sync)"
    assert len(rd.long_run_finishes) == 1


def test_no_long_runs_is_no_data(db):
    race(db)
    run(db, LONG_DAY, 12.0)
    rd, it = finishes(db)
    assert it.status == "no_data" and rd.long_run_finishes == []
    assert it.rule == "No run of 28 km or more in the block yet"


def test_excluded_long_run_does_not_appear(db):
    race(db)
    a = run(db, LONG_DAY, 32.0)
    splits(db, a, [310, 310, 290, 290])
    a.exclude_from_analysis = True
    db.commit()
    rd, it = finishes(db)
    assert rd.long_runs == [] and rd.long_run_finishes == []
    assert it.status == "no_data"
