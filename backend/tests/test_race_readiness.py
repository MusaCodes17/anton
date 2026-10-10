"""R8.4.4 — "am I ready for race X?": the readiness checklist in race_advisor.

Rules under test: no race ahead → has_race false and an empty checklist (the
roadmap's exit criterion — the card hides); which race is "next" (skipped
never, completed only before its date); the block's edges (its first Monday
counts, race-day running doesn't); the distance-relative long-run threshold at
its exact boundary (28.0 km counts for a marathon, 27.9 doesn't); 3 long runs
needed; longest run at exactly the target; the key effort vs. target pace
(at-or-faster is met, slower or missing is not_met, no target is n/a); the
8-week effort window; n/a before the block starts and for a race with no
distance; read-only (no prune); REST and MCP agree. All tests pin `as_of`.
"""
from contextlib import contextmanager
from datetime import date, timedelta

from app import mcp_server
from app.models.models import Activity, ActivityBestEffort, ActivityEffortScan, PlannedRace
from app.routers.races import get_race_readiness
from app.services.race_advisor import race_block_context, race_readiness

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


def test_no_recent_key_effort_is_not_met_and_old_efforts_drop_out(db):
    race(db)
    effort(db, AS_OF - timedelta(weeks=8), "half", 4800)            # one day outside the window
    effort(db, AS_OF - timedelta(days=10), "10k", 2400)             # inside, but not the key distance
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.effort_window_start == "2026-08-15"
    assert [e.label for e in rd.recent_efforts] == ["10k"]
    ke = items(rd)["key_effort"]
    assert ke.status == "not_met" and ke.value is None


def test_no_target_lists_efforts_without_a_comparison(db):
    race(db, target_s=None)
    effort(db, AS_OF - timedelta(days=20), "half", 5000)
    rd = race_readiness(db, as_of=AS_OF)
    assert rd.recent_efforts[0].vs_target_s_per_km is None
    ke = items(rd)["key_effort"]
    assert ke.status == "n/a" and "No target time" in ke.rule


# --- surfaces ---------------------------------------------------------------------------------

def test_race_block_context_carries_readiness(db):
    race(db)
    ctx = race_block_context(db, today=AS_OF)
    assert ctx.readiness.has_race and ctx.readiness.race.name == ctx.next_race.name


def test_endpoint_and_mcp_tool_agree(db, monkeypatch):
    race(db)
    run(db, date(2026, 9, 13), 32.0)
    effort(db, AS_OF - timedelta(days=20), "half", 5300)

    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)

    rest = get_race_readiness(as_of=AS_OF, db=db).model_dump()
    mcp = mcp_server.get_race_block_context(as_of=AS_OF.isoformat())["readiness"]
    assert rest == mcp
    assert rest["has_race"] is True and rest["heuristic"] is True
    assert [i["key"] for i in rest["checklist"]] == [
        "weeks_to_go", "peak_week", "longest_run", "long_runs", "key_effort"]


def test_endpoint_without_a_race_says_so(db):
    assert get_race_readiness(as_of=AS_OF, db=db).model_dump()["has_race"] is False


def test_mcp_tool_rejects_a_bad_date():
    assert "error" in mcp_server.get_race_block_context(as_of="next sunday")
