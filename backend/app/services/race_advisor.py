"""
Race-block training advisor (R3.6) and race readiness (R8.4.4).

Assembles the structured context a training-block advisor needs: next race
countdown, recent weekly volumes, rotation pipeline state, and the latest
fitness snapshot. Read-only — no invariants are touched.

R8.4.4 adds `race_readiness` — "am I ready for race X?" — as a checklist with
numbers (weeks to go, peak week, longest run, long-run count, a recent effort
vs. target pace), never a score. It lives here, not in a parallel service, so
the race_block_advisor prompt and the Training page read the same answer
(REST `GET /api/races/readiness`; MCP `get_race_block_context.readiness`).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.models import PlannedRace
from app.services import activities as activities_svc
from app.services import fitness as fitness_svc
from app.services import races as races_svc
from app.services import rotation as rotation_svc
from app.services import strava_stats
from app.services import training_trends
from app.utils.pace import seconds_to_pace


@dataclass
class RaceInfo:
    name: str
    race_date: str           # ISO date
    distance_km: Optional[float]
    days_to_race: int
    weeks_to_race: int
    target_pace: Optional[str]   # "M:SS/km" if target time + distance set
    target_time_s: Optional[int]


@dataclass
class WeekVolume:
    period: str              # ISO week key (e.g. "2026-W28")
    total_km: float
    run_count: int
    avg_pace: Optional[str]  # "M:SS/km"
    avg_hr: Optional[int]


@dataclass
class PipelineShoe:
    shoe_id: int
    brand: str
    model: str
    nickname: Optional[str]
    shoe_type: Optional[str]
    pct: float               # 0..1+
    current_mileage: float
    mileage_limit: float
    replacement_deals: int
    forecast_status: str = "idle"                 # on_track | idle | overdue (R6.2)
    weekly_km: float = 0.0
    weeks_to_limit: Optional[float] = None
    projected_limit_date: Optional[str] = None


@dataclass
class FitnessSnapshot:
    vo2max: Optional[float]
    threshold_pace: Optional[str]    # "M:SS/km"
    race_predictions: Optional[dict] # {distance_km_str: predicted_time_s}
    running_level: Optional[float]
    captured_at: Optional[str]       # ISO date


@dataclass
class RaceBlockContext:
    has_next_race: bool
    next_race: Optional[RaceInfo]

    recent_weeks: list    # list[WeekVolume], newest-first
    avg_weekly_km: float  # mean over the window

    pipeline: list        # list[PipelineShoe], pct-descending

    has_fitness: bool
    fitness: Optional[FitnessSnapshot]

    readiness: Optional["RaceReadiness"] = None   # R8.4.4 — the checklist, same as REST


def race_block_context(
    db: Session,
    *,
    today: Optional[date] = None,
    weeks_back: int = 12,
) -> RaceBlockContext:
    """
    Compile the race-block training context for the advisor prompt.

    Identifies the soonest upcoming race, returns the last `weeks_back` weeks
    of weekly volume, the current retirement pipeline, and the latest COROS
    fitness snapshot, plus the R8.4.4 readiness checklist for `today`. All
    reads — no writes, no invariants touched.

    Args:
        db:         Active database session.
        today:      Reference date (defaults to today in Toronto — run dates are
                    Toronto local dates, and REST readiness uses the same day).
                    Injected in tests.
        weeks_back: Number of recent weekly buckets to include (default 12).
    """
    today = today or toronto_today()

    # Soonest upcoming race with days_remaining ≥ 0 and not done (completed or DNF)
    all_races = races_svc.list_races(db, today)
    upcoming = [
        r for r in all_races
        if r.days_remaining >= 0 and getattr(r, "status", None) not in races_svc.DONE_STATUSES
    ]
    next_race: Optional[RaceInfo] = None
    if upcoming:
        r = min(upcoming, key=lambda x: x.days_remaining)
        next_race = RaceInfo(
            name=r.name,
            race_date=(
                r.race_date.isoformat()
                if hasattr(r.race_date, "isoformat")
                else str(r.race_date)
            ),
            distance_km=r.distance_km,
            days_to_race=r.days_remaining,
            weeks_to_race=r.weeks_remaining,
            target_pace=getattr(r, "target_pace", None),
            target_time_s=getattr(r, "target_time_s", None),
        )

    # Last `weeks_back` weekly volume buckets (newest-first from training_summary)
    all_weeks = strava_stats.training_summary(db, period="weekly")
    recent_weeks = [
        WeekVolume(
            period=s.period,
            total_km=s.total_km,
            run_count=s.run_count,
            avg_pace=s.avg_pace,
            avg_hr=s.avg_hr,
        )
        for s in all_weeks[:weeks_back]
    ]
    avg_km = (
        round(sum(w.total_km for w in recent_weeks) / len(recent_weeks), 2)
        if recent_weeks
        else 0.0
    )

    # Retirement pipeline — ≥ 75% shoes, pct-descending (rotation_svc owns the threshold)
    pipeline = [
        PipelineShoe(
            shoe_id=e.shoe.id,
            brand=e.shoe.brand,
            model=e.shoe.model,
            nickname=e.shoe.nickname,
            shoe_type=getattr(e.shoe, "shoe_type", None),
            pct=e.pct,
            current_mileage=e.current_mileage,
            mileage_limit=e.mileage_limit,
            replacement_deals=e.replacement_deals,
            forecast_status=e.forecast_status,
            weekly_km=e.weekly_km,
            weeks_to_limit=e.weeks_to_limit,
            projected_limit_date=e.projected_limit_date,
        )
        for e in rotation_svc.retirement_pipeline(db)
    ]

    # Latest fitness snapshot (optional — may not have been synced yet)
    snap = fitness_svc.latest(db)
    fitness: Optional[FitnessSnapshot] = None
    if snap:
        fitness = FitnessSnapshot(
            vo2max=snap.vo2max,
            threshold_pace=(
                seconds_to_pace(snap.threshold_pace_s_per_km)
                if snap.threshold_pace_s_per_km
                else None
            ),
            race_predictions=snap.race_predictions,
            running_level=snap.running_level,
            captured_at=(
                fitness_svc.captured_local_date(snap).isoformat() if snap.captured_at else None
            ),
        )

    return RaceBlockContext(
        readiness=race_readiness(db, as_of=today),
        has_next_race=next_race is not None,
        next_race=next_race,
        recent_weeks=recent_weeks,
        avg_weekly_km=avg_km,
        pipeline=pipeline,
        has_fitness=fitness is not None,
        fitness=fitness,
    )


# ═══════════════════════════════════════════════════════════════════════════
# R8.4.4 — "Am I ready for race X?" (roadmap §R8.4)
# ═══════════════════════════════════════════════════════════════════════════
#
# A checklist with numbers, not a score: each item states its rule and its
# numbers, and is met / not_met / info / n/a. Every threshold below is a
# heuristic from common training practice, labelled as such on every surface —
# not a physiological model. Read-only; nothing is stored (INV-7).

_TZ = ZoneInfo("America/Toronto")   # run dates are Toronto local dates (CLAUDE.md §6)

STATUS_MET = "met"
STATUS_NOT_MET = "not_met"
STATUS_INFO = "info"        # a number worth seeing, with no pass/fail rule
STATUS_NA = "n/a"           # the rule can't apply (no target, no distance, block not started)
# The rule applies but there is no evidence yet — never shown as not_met
# ("no data is never not met"): not_met means evidence exists and falls short.
STATUS_NO_DATA = "no_data"
STATUSES = (STATUS_MET, STATUS_NOT_MET, STATUS_INFO, STATUS_NA, STATUS_NO_DATA)


@dataclass(frozen=True)
class RaceClass:
    """Distance-relative readiness thresholds for one kind of race (heuristic)."""
    name: str                   # marathon | half | 10k | 5k
    min_distance_km: float      # a race at least this long falls in the class
    block_weeks: int            # the block: this many calendar weeks ending with race week
    long_run_km: float          # a run at least this long counts as a long run
    longest_target_km: float    # "longest run" is met at or above this
    key_effort: str             # EFFORT_DISTANCES label compared with target pace
    effort_labels: tuple        # best-effort labels listed for the race


# The block is a fixed number of calendar weeks ending with race week, not
# "since the previous race": a marathon build usually contains a tune-up half,
# and cutting the block there would hide most of it. Lengths are common plan
# lengths (16 weeks for a marathon, 12 for a half, 8–10 for 5k/10k).
#
# Long runs: ≥ 28 km is the roadmap's marathon line (≈ 2/3 of the distance);
# the shorter races use a run well past ~3/4 of race distance (half) or past
# race distance (10k, 5k), where the aerobic work of the block happens. The
# longest-run targets are the classic peak long runs (32 / 18 / 15 / 10 km).
#
# Key effort: the recent best effort at about HALF the race distance compared
# with goal pace — "have I recently held race pace for half the race?". A 5k
# at marathon pace says little; a half at marathon pace says a lot.
RACE_CLASSES: tuple[RaceClass, ...] = (
    # Ultras (> 42.2 km) fall in "marathon": the archive has none, and the
    # marathon's thresholds are the honest floor for anything longer.
    RaceClass("marathon", 30.0, 16, 28.0, 32.0, "half", ("10k", "half")),
    RaceClass("half", 15.0, 12, 16.0, 18.0, "10k", ("5k", "10k", "half")),
    RaceClass("10k", 8.0, 10, 12.0, 15.0, "5k", ("5k", "10k")),
    RaceClass("5k", 0.0, 8, 8.0, 10.0, "mile", ("1k", "mile", "5k")),
)
DEFAULT_BLOCK_WEEKS = 12    # race with no distance → no class; a middle-of-the-road block
LONG_RUNS_NEEDED = 3        # three long runs make a habit; one is a one-off
GAP_DAYS = 7                # a week off is an interruption worth explaining (heuristic); the parked training notes / R11.4 reasons would explain it
RECENT_EFFORT_WEEKS = 8     # "recent" bests: ~2 months — older efforts describe a different you


@dataclass
class ReadinessRace:
    id: int
    name: str
    race_date: str                    # ISO date
    distance_km: Optional[float]
    status: str
    days_to_race: int
    weeks_to_race: int                # days // 7, as races.attach_derived
    target_time_s: Optional[int]
    target_pace: Optional[str]        # "M:SS/km"
    target_pace_s_per_km: Optional[int]


@dataclass
class ReadinessWeek:
    period: str                       # ISO week key ("2026-W37"), as the Volume chart
    total_km: float
    run_count: int


@dataclass
class ReadinessRun:
    run_date: str                     # ISO date
    distance_km: float
    name: Optional[str]
    activity_id: Optional[int]


@dataclass
class ReadinessEffort:
    label: str                        # EFFORT_DISTANCES label
    distance_km: float
    time_s: int                       # elapsed time over the distance (the records clock)
    pace: str                         # "M:SS/km"
    pace_s_per_km: int
    vs_target_s_per_km: Optional[int] # effort pace − target pace; negative = faster than target
    run_date: Optional[str]
    name: Optional[str]
    activity_id: Optional[int]
    segment: bool                     # a stretch inside a longer run (R8.2)


@dataclass
class EvidenceRun:
    """A run behind a checklist number (R11.1), so the page can drill down."""
    activity_id: Optional[int]
    run_date: str                     # ISO date
    distance_km: float                # rounded 1 dp; for a segment, the stretch's distance
    name: Optional[str]
    segment: bool = False             # the number is a stretch inside a longer run (R8.2)


@dataclass
class ChecklistItem:
    key: str                          # weeks_to_go | peak_week | longest_run | long_runs | key_effort
    label: str
    status: str                       # one of STATUSES
    rule: Optional[str]               # the stated rule (or why it can't apply)
    value: Optional[float]            # the runner's number
    target: Optional[float]           # the rule's number, when there is one
    unit: str                         # weeks | km | runs | s/km (pace: lower is faster)
    period_from: Optional[str] = None  # ISO date, inclusive: the period the number was computed over
    period_to: Optional[str] = None    # ISO date, inclusive
    evidence: list = field(default_factory=list)   # list[EvidenceRun] behind the number
    age_days: Optional[int] = None     # key_effort only: days from the effort's run to as_of


@dataclass
class Gap:
    """A stretch of GAP_DAYS+ consecutive days without a run inside the block (R11.3)."""
    start: str                        # ISO date, first day off
    end: str                          # ISO date, last day off
    days: int


@dataclass
class Consistency:
    """How steadily the block was run (R11.3). Descriptive — no pass/fail."""
    weeks_elapsed: int                # Monday-aligned weeks from block_start through block_end's week
    weeks_with_runs: int              # of those, weeks with at least one run
    median_runs_per_week: float       # zero weeks included; 1 dp
    gaps: list = field(default_factory=list)   # list[Gap], oldest first


@dataclass
class TaperWeek:
    offset: int                       # -2, -1, 0 (0 = race week), as BlockWeek.offset
    week_start: str                   # ISO Monday
    km: float                         # runs on or before block_end (race week is partial)
    pct_of_peak: Optional[int]        # None when the block has no peak week
    complete: bool                    # the week's Sunday <= block_end


@dataclass
class Taper:
    """The final TAPER_DAYS: each of the last three weeks against the block's
    peak week, plus recency of the last long run / key effort (R11.3). Numbers
    to set beside past builds — there is no target percentage."""
    peak_week_km: Optional[float]
    weeks: list = field(default_factory=list)   # list[TaperWeek], oldest first
    days_since_long_run: Optional[int] = None   # to block_end; None if none in the block
    days_since_key_effort: Optional[int] = None # the key_effort item's age_days


@dataclass
class PastBuild:
    """One past race of the readiness race's class, with its build cut at the
    same number of days before its race as today's block is (R11.2). Numbers
    beside a result — no ranking, no verdict."""
    race: BlockRace
    result_vs_target_s: Optional[int]  # result − target; negative = faster than target; None without both (DNF)
    cut_date: str                      # ISO — the past block's end at the cut
    km: float                          # cumulative block km up to the cut
    runs: int
    long_runs: int
    longest_km: Optional[float]        # None with no runs
    peak_week_km: Optional[float]      # None with no runs
    consistency: Optional[Consistency] = None   # the same numbers at the same cut (R11.3)
    taper: Optional[Taper] = None


@dataclass
class RaceReadiness:
    """"Am I ready for race X?" for the next race. `has_race` False means there
    is no race ahead: every other field is empty and the readiness card hides."""
    has_race: bool
    as_of: str                        # ISO date the answer is for
    race: Optional[ReadinessRace] = None
    race_class: Optional[str] = None  # RaceClass.name; None when the race has no distance
    block_weeks: Optional[int] = None
    block_start: Optional[str] = None # Monday, block_weeks − 1 weeks before race week's Monday
    block_end: Optional[str] = None   # min(as_of, the day before the race), inclusive
    block_started: bool = False
    block_km: float = 0.0
    block_runs: int = 0
    peak_week: Optional[ReadinessWeek] = None
    current_week: Optional[ReadinessWeek] = None   # the ISO week holding block_end
    longest_run: Optional[ReadinessRun] = None
    long_run_km: Optional[float] = None
    long_runs_needed: int = LONG_RUNS_NEEDED
    long_runs: list = field(default_factory=list)       # list[ReadinessRun], oldest first
    effort_window_start: Optional[str] = None
    key_effort: Optional[str] = None
    recent_efforts: list = field(default_factory=list)  # list[ReadinessEffort], shortest first
    checklist: list = field(default_factory=list)       # list[ChecklistItem]
    days_before_race: Optional[int] = None   # race_date − block_end; set when the block has started
    past_builds: list = field(default_factory=list)     # list[PastBuild], newest race first
    consistency: Optional[Consistency] = None           # set when the block has started (R11.3)
    taper: Optional[Taper] = None                       # only within training_trends.TAPER_DAYS of the race
    heuristic: bool = True


def toronto_today() -> date:
    return datetime.now(_TZ).date()


def race_class_for(distance_km: Optional[float]) -> Optional[RaceClass]:
    """The class a race distance falls in; None when the race has no distance."""
    if not distance_km:
        return None
    return next(c for c in RACE_CLASSES if distance_km >= c.min_distance_km)


def block_window(race_date: date, distance_km: Optional[float]) -> tuple[Optional[RaceClass], int, date]:
    """The block definition shared by readiness and the block comparison:
    (class, block_weeks, block_start). The block is `block_weeks` calendar weeks
    (Monday-aligned) ending with race week; block_start is that first Monday."""
    cls = race_class_for(distance_km)
    block_weeks = cls.block_weeks if cls else DEFAULT_BLOCK_WEEKS
    race_monday = race_date - timedelta(days=race_date.weekday())
    block_start = race_monday - timedelta(weeks=block_weeks - 1)
    return cls, block_weeks, block_start


def _readiness_race(db: Session, as_of: date) -> Optional[PlannedRace]:
    """The race readiness is about: the soonest race on or after `as_of` that
    isn't skipped or DNF (a DNF'd race was started and is over, so it can't be
    the one you're getting ready for). A direct read, not races.list_races (which prunes stale plans — a
    write). A *completed* race still counts while `as_of` is before its date:
    that only happens when asking about the past ("was I ready for the Spring
    Half?"), and it was a planned race then. On race day a completed race is
    done, so it's left out."""
    return (
        db.query(PlannedRace)
        .filter(
            PlannedRace.race_date >= as_of,
            PlannedRace.status.notin_(("skipped", "dnf")),
            or_(PlannedRace.status != "completed", PlannedRace.race_date > as_of),
        )
        .order_by(PlannedRace.race_date.asc(), PlannedRace.id.asc())
        .first()
    )


def _run(r) -> ReadinessRun:
    return ReadinessRun(run_date=r.date.isoformat(), distance_km=round(r.distance_km, 1),
                        name=r.name, activity_id=r.activity_id)


def race_readiness(db: Session, *, as_of: Optional[date] = None) -> RaceReadiness:
    """
    The readiness checklist for the next race on or after `as_of` (default:
    today in Toronto). Items, each with its stated rule and numbers:

    - weeks_to_go (info) — days // 7 to race day.
    - peak_week (info) — the biggest ISO week of the block, in km.
    - longest_run — met when the block's longest run ≥ the class target.
    - long_runs — met when ≥ LONG_RUNS_NEEDED block runs reach the class
      long-run distance (28 km for a marathon). Exactly the threshold counts.
    - key_effort — the best effort at ~half race distance over the last
      RECENT_EFFORT_WEEKS weeks vs. target pace: met at or faster than target
      pace; not_met when slower; no_data when there's no such effort; n/a
      with no target time.

    Status honesty (R11.1): `not_met` only when evidence exists and falls
    short; a started block with no runs (or no key effort in the window) is
    `no_data`. Every item except weeks_to_go carries `period_from`/`period_to`
    (the span it was computed over) and `evidence` (the runs behind the
    number); key_effort also carries `age_days`.

    R11.3 appends descriptive `info` items once the block has started (no
    pass/fail, no target percentages): weeks_with_running, gaps (breaks of
    GAP_DAYS+ days), and — only within training_trends.TAPER_DAYS of the race —
    taper_volume and since_long_run. Their numbers also sit on `consistency` /
    `taper` and on each past build at the same cut.

    The block is read from `block_start` up to `as_of`, never past the day
    before the race (race-day running isn't training for it). Before the block
    starts its items are n/a; a race with no distance has no class, so the
    distance-relative items are n/a. Best efforts come from
    strava_stats.personal_bests over the effort window, so they follow the
    Records card's rules exactly. Read-only — no prune, no writes.
    """
    as_of = as_of or toronto_today()
    race = _readiness_race(db, as_of)
    if race is None:
        return RaceReadiness(has_race=False, as_of=as_of.isoformat())

    cls, block_weeks, block_start = block_window(race.race_date, race.distance_km)
    block_end = min(as_of, race.race_date - timedelta(days=1))
    started = block_start <= block_end

    days = (race.race_date - as_of).days
    target_s_per_km = (
        race.target_time_s / race.distance_km if race.target_time_s and race.distance_km else None
    )
    out = RaceReadiness(
        has_race=True,
        as_of=as_of.isoformat(),
        race=ReadinessRace(
            id=race.id, name=race.name, race_date=race.race_date.isoformat(),
            distance_km=race.distance_km, status=race.status,
            days_to_race=days, weeks_to_race=days // 7,
            target_time_s=race.target_time_s,
            target_pace=seconds_to_pace(target_s_per_km) if target_s_per_km else None,
            target_pace_s_per_km=round(target_s_per_km) if target_s_per_km else None,
        ),
        race_class=cls.name if cls else None,
        block_weeks=block_weeks,
        block_start=block_start.isoformat(),
        block_end=block_end.isoformat(),
        block_started=started,
        long_run_km=cls.long_run_km if cls else None,
        key_effort=cls.key_effort if cls else None,
    )

    # ── the block: volume, peak week, long runs ───────────────────────────────
    block_runs: list = []   # raw rows, for checklist evidence only (not in the payload)
    if started:
        runs = [r for r in activities_svc.unified_activities(db, date_from=block_start, date_to=block_end)
                if r.distance_km]
        weeks = strava_stats.training_summary(db, "weekly", date_from=block_start, date_to=block_end)
        out.block_runs = len(runs)
        out.block_km = round(sum(r.distance_km for r in runs), 1)
        if weeks:
            # newest-first, so on a tie max() keeps the most recent week
            peak = max(weeks, key=lambda w: w.total_km)
            out.peak_week = ReadinessWeek(peak.period, round(peak.total_km, 1), peak.run_count)
        iso = block_end.isocalendar()
        current_key = f"{iso[0]}-W{iso[1]:02d}"
        cur = next((w for w in weeks if w.period == current_key), None)
        out.current_week = ReadinessWeek(current_key, round(cur.total_km, 1) if cur else 0.0,
                                         cur.run_count if cur else 0)
        block_runs = runs
        if runs:
            out.longest_run = _run(max(runs, key=lambda r: r.distance_km))
        if cls:
            out.long_runs = [_run(r) for r in sorted(runs, key=lambda r: r.date)
                             if r.distance_km >= cls.long_run_km]

    # ── recent best efforts vs. target pace ───────────────────────────────────
    effort_from = as_of - timedelta(weeks=RECENT_EFFORT_WEEKS) + timedelta(days=1)
    out.effort_window_start = effort_from.isoformat()
    if cls and effort_from <= block_end:
        bests = strava_stats.personal_bests(db, date_from=effort_from, date_to=block_end).best_efforts
        for b in bests:
            if b.band not in cls.effort_labels:
                continue
            pace_s = b.total_time_s / b.distance_km
            out.recent_efforts.append(ReadinessEffort(
                label=b.band, distance_km=b.distance_km, time_s=b.total_time_s,
                pace=b.avg_pace, pace_s_per_km=round(pace_s),
                vs_target_s_per_km=round(pace_s - target_s_per_km) if target_s_per_km else None,
                run_date=b.run_date, name=b.name, activity_id=b.activity_id, segment=b.segment,
            ))

    out.checklist = _checklist(out, cls, block_runs)

    if started:
        out.consistency = _consistency([r.date for r in block_runs], block_start, block_end)
        key_item = next((i for i in out.checklist if i.key == "key_effort"), None)
        if cls:
            out.taper = _taper(
                block_runs, race.race_date, block_start, block_end,
                out.peak_week.total_km if out.peak_week else None, as_of,
                long_run_km=cls.long_run_km,
                key_effort_age_days=key_item.age_days if key_item else None,
            )
        out.checklist.extend(_descriptive_items(out, block_runs, cls))

    if started and cls:
        d = (race.race_date - block_end).days   # >= 1: block_end <= race_date − 1
        out.days_before_race = d
        # Whole-table cost: one unified_activities read per past block (two since
        # R11.3, which re-reads the block's runs for consistency/taper because
        # _build_block doesn't return them), filtered in Python — fine at
        # personal scale (a handful of races of a class).
        for e in reversed(_class_entries(db, cls, as_of)):
            if e.id == race.id or e.race_date >= as_of or e.status not in races_svc.DONE_STATUSES:
                continue
            _, bw, bstart = block_window(e.race_date, e.distance_km)
            # as_of = race_date − d makes _build_block cut block_end at race_date − d.
            b = _build_block(db, e, cls, bw, bstart, as_of=e.race_date - timedelta(days=d))
            b_end = date.fromisoformat(b.block_end)
            b_runs = ([r for r in activities_svc.unified_activities(db, date_from=bstart, date_to=b_end)
                       if r.distance_km] if bstart <= b_end else [])
            b_peak = b.peak_week.km if b.peak_week else None
            out.past_builds.append(PastBuild(
                race=b.race,
                result_vs_target_s=(e.result_time_s - e.target_time_s
                                    if e.result_time_s is not None and e.target_time_s is not None else None),
                cut_date=b.block_end, km=b.total_km, runs=b.runs, long_runs=b.long_runs,
                longest_km=b.longest_run.distance_km if b.longest_run else None,
                peak_week_km=b_peak,
                consistency=_consistency([r.date for r in b_runs], bstart, b_end),
                # as_of = race_date − d, so the taper gate matches today's exactly.
                # key-effort age isn't derived for past builds (no effort scan per block).
                taper=_taper(b_runs, e.race_date, bstart, b_end, b_peak,
                             e.race_date - timedelta(days=d), long_run_km=cls.long_run_km),
            ))
    return out


def _evidence(r) -> EvidenceRun:
    return EvidenceRun(activity_id=r.activity_id, run_date=r.date.isoformat(),
                       distance_km=round(r.distance_km, 1), name=r.name)


def _checklist(rd: RaceReadiness, cls: Optional[RaceClass], block_runs: Optional[list] = None) -> list[ChecklistItem]:
    """The checklist rows, in reading order. Rules are stated in words so every
    surface (page, MCP, Son of Anton) explains a status the same way. `block_runs`
    are the raw unified-activity rows of the block, used for peak-week evidence."""
    race = rd.race
    block_runs = block_runs or []
    items = [ChecklistItem(
        key="weeks_to_go", label="Weeks to go", status=STATUS_INFO,
        rule=f"{race.days_to_race} days to race day", value=race.weeks_to_race, target=None, unit="weeks",
    )]

    not_started = None if rd.block_started else f"The {rd.block_weeks}-week block starts {rd.block_start}"
    no_class = "The race has no distance, so there's no distance-relative rule"
    block_period = dict(period_from=rd.block_start, period_to=rd.block_end)
    no_runs = rd.block_started and not block_runs   # started, but nothing to compute from

    peak_evidence: list = []
    if not rd.block_started:
        peak_rule = not_started
    elif rd.peak_week:
        peak_rule = (f"Biggest ISO week of the block ({rd.peak_week.period}); "
                     f"this week so far {rd.current_week.total_km:g} km")
        peak_evidence = [
            _evidence(r) for r in sorted(block_runs, key=lambda r: r.date)
            if "{}-W{:02d}".format(*r.date.isocalendar()[:2]) == rd.peak_week.period
        ]
    else:
        peak_rule = "No running in the block yet"
    items.append(ChecklistItem(
        key="peak_week", label="Peak week",
        status=(STATUS_NO_DATA if no_runs or (rd.block_started and not rd.peak_week)
                else STATUS_INFO if rd.block_started else STATUS_NA),
        rule=peak_rule,
        value=rd.peak_week.total_km if rd.peak_week else None, target=None, unit="km",
        evidence=peak_evidence, **block_period,
    ))

    def gate() -> Optional[tuple[str, str]]:
        """(status, why) when a block rule can't apply or has no evidence, else None."""
        if cls is None:
            return STATUS_NA, no_class
        if not rd.block_started:
            return STATUS_NA, not_started
        if no_runs:
            return STATUS_NO_DATA, "No runs in the block yet"
        return None

    longest = rd.longest_run.distance_km if rd.longest_run else None
    status, rule = gate() or (
        STATUS_MET if (longest or 0) >= cls.longest_target_km else STATUS_NOT_MET,
        f"Longest run in the block at least {cls.longest_target_km:g} km",
    )
    longest_ev = []
    if rd.longest_run:
        lr = rd.longest_run
        longest_ev = [EvidenceRun(activity_id=lr.activity_id, run_date=lr.run_date,
                                  distance_km=lr.distance_km, name=lr.name)]
    items.append(ChecklistItem(
        key="longest_run", label="Longest run", status=status, rule=rule,
        value=longest, target=cls.longest_target_km if cls else None, unit="km",
        evidence=longest_ev, **block_period,
    ))

    status, rule = gate() or (
        STATUS_MET if len(rd.long_runs) >= rd.long_runs_needed else STATUS_NOT_MET,
        f"At least {rd.long_runs_needed} runs of {cls.long_run_km:g} km or more in the block",
    )
    items.append(ChecklistItem(
        key="long_runs",
        label=f"Long runs ≥ {cls.long_run_km:g} km" if cls else "Long runs",
        status=status, rule=rule,
        value=len(rd.long_runs) if cls and rd.block_started else None,
        target=rd.long_runs_needed if cls else None, unit="runs",
        evidence=[EvidenceRun(activity_id=lr.activity_id, run_date=lr.run_date,
                              distance_km=lr.distance_km, name=lr.name) for lr in rd.long_runs],
        **block_period,
    ))

    # Key effort: needs a class (which distance) and a target (which pace).
    effort = next((e for e in rd.recent_efforts if e.label == rd.key_effort), None)
    if cls is None:
        status, rule = STATUS_NA, no_class
    elif race.target_pace_s_per_km is None:
        status, rule = STATUS_NA, "No target time set, so there's no target pace to compare with"
    elif effort is None:
        status = STATUS_NO_DATA
        rule = f"No {cls.key_effort} effort recorded since {rd.effort_window_start}"
    else:
        status = STATUS_MET if effort.pace_s_per_km <= race.target_pace_s_per_km else STATUS_NOT_MET
        rule = (f"Best {cls.key_effort} effort since {rd.effort_window_start} "
                f"at or faster than target pace ({race.target_pace})")
    effort_ev, age = [], None
    if effort and effort.run_date:
        effort_ev = [EvidenceRun(activity_id=effort.activity_id, run_date=effort.run_date,
                                 distance_km=round(effort.distance_km, 1), name=effort.name,
                                 segment=effort.segment)]
        age = (date.fromisoformat(rd.as_of) - date.fromisoformat(effort.run_date)).days
    items.append(ChecklistItem(
        key="key_effort",
        label=f"Recent {cls.key_effort} effort vs. target pace" if cls else "Recent effort vs. target pace",
        status=status, rule=rule,
        value=effort.pace_s_per_km if effort else None,
        target=race.target_pace_s_per_km if cls else None, unit="s/km",
        period_from=rd.effort_window_start, period_to=rd.block_end,
        evidence=effort_ev, age_days=age,
    ))
    return items


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _consistency(run_dates: list, block_start: date, block_end: date) -> Consistency:
    """Weeks-with-running, median runs a week and breaks of GAP_DAYS+ days over
    [block_start, block_end]. Pure (no DB), shared by the current block and
    each past build so the numbers are comparable. Weeks are Monday-aligned and
    a partial current week counts; the median includes zero weeks. Gaps are
    measured between runs with the block edges as sentinels, so time before the
    first run or after the last (ongoing) counts too."""
    n_weeks = (_monday(block_end) - block_start).days // 7 + 1
    per_week = [0] * n_weeks
    for d in run_dates:
        if block_start <= d <= block_end:
            per_week[(_monday(d) - block_start).days // 7] += 1

    edges = ([block_start - timedelta(days=1)]
             + sorted({d for d in run_dates if block_start <= d <= block_end})
             + [block_end + timedelta(days=1)])
    gaps = []
    for a, b in zip(edges, edges[1:]):
        days = (b - a).days - 1
        if days >= GAP_DAYS:
            gaps.append(Gap(start=(a + timedelta(days=1)).isoformat(),
                            end=(b - timedelta(days=1)).isoformat(), days=days))
    return Consistency(
        weeks_elapsed=n_weeks, weeks_with_runs=sum(1 for c in per_week if c),
        median_runs_per_week=round(float(statistics.median(per_week)), 1), gaps=gaps,
    )


def _taper(runs: list, race_date: date, block_start: date, block_end: date,
           peak_week_km: Optional[float], as_of: date, *, long_run_km: Optional[float] = None,
           key_effort_age_days: Optional[int] = None) -> Optional[Taper]:
    """The taper numbers, or None unless the race is within
    training_trends.TAPER_DAYS of `as_of`. Pure (no DB). Weeks are race week
    (offset 0, Monday-aligned) and the two before; km counts runs on or before
    block_end, so race week is partial and a week that hasn't started reads
    0.0 with complete=False. Descriptive: no target percentage."""
    if (race_date - as_of).days > training_trends.TAPER_DAYS:
        return None
    race_monday = _monday(race_date)
    weeks = []
    for offset in (-2, -1, 0):
        ws = race_monday + timedelta(weeks=offset)
        km = round(sum(r.distance_km for r in runs
                       if ws <= r.date < ws + timedelta(days=7) and block_start <= r.date <= block_end), 1)
        weeks.append(TaperWeek(
            offset=offset, week_start=ws.isoformat(), km=km,
            pct_of_peak=round(100 * km / peak_week_km) if peak_week_km else None,
            complete=ws + timedelta(days=6) <= block_end,
        ))
    last_long = max((r.date for r in runs if long_run_km is not None and r.distance_km >= long_run_km
                     and block_start <= r.date <= block_end), default=None)
    return Taper(
        peak_week_km=peak_week_km, weeks=weeks,
        days_since_long_run=(block_end - last_long).days if last_long else None,
        days_since_key_effort=key_effort_age_days,
    )


def _descriptive_items(rd: RaceReadiness, block_runs: list, cls: Optional[RaceClass]) -> list[ChecklistItem]:
    """R11.3 checklist rows — consistency, and the taper inside TAPER_DAYS. All
    `info`: descriptive numbers with no pass/fail rule and no target
    percentages. Only called once the block has started."""
    period = dict(period_from=rd.block_start, period_to=rd.block_end)
    c = rd.consistency
    items = [
        ChecklistItem(
            key="weeks_with_running", label="Weeks with running", status=STATUS_INFO,
            rule=f"{c.weeks_with_runs} of {c.weeks_elapsed} weeks had a run; "
                 f"median {c.median_runs_per_week:g} runs a week",
            value=c.weeks_with_runs, target=None, unit="weeks", **period),
        ChecklistItem(
            key="gaps", label=f"Breaks of {GAP_DAYS}+ days", status=STATUS_INFO,
            rule=("; ".join(f"{g.start} → {g.end} ({g.days} days)" for g in c.gaps)
                  or f"No break of {GAP_DAYS}+ days"),
            value=len(c.gaps), target=None, unit="breaks", **period),
    ]
    t = rd.taper
    if t is not None:
        done = [w for w in t.weeks if w.complete]
        parts = []
        for w in t.weeks:
            if w.week_start > rd.block_end:
                continue   # hasn't started
            pct = f"{w.pct_of_peak}%" if w.pct_of_peak is not None else "n/a"
            name = f"week \u2212{-w.offset}" if w.offset else "race week so far"
            parts.append(f"{name}: {pct}")
        peak = f"{t.peak_week_km:g} km" if t.peak_week_km is not None else "n/a"
        items.append(ChecklistItem(
            key="taper_volume", label="Taper volume", status=STATUS_INFO,
            rule=f"Peak week {peak}. " + ", ".join(parts),
            value=done[-1].pct_of_peak if done else None, target=None, unit="% of peak", **period))
        last_long = None
        if cls:
            longs = [r for r in block_runs if r.distance_km >= cls.long_run_km]
            last_long = max(longs, key=lambda r: r.date, default=None)
        items.append(ChecklistItem(
            key="since_long_run", label="Days since last long run", status=STATUS_INFO,
            rule=(f"Last run of {cls.long_run_km:g} km or more: {last_long.date.isoformat()}"
                  if last_long else "No long run in the block"),
            value=t.days_since_long_run, target=None, unit="days",
            evidence=[_evidence(last_long)] if last_long else [], **period))
    return items


# ═══════════════════════════════════════════════════════════════════════════
# R10.2 — race-block retrospective: the blocks before past races, side by side
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class BlockRace:
    """The race a block led up to (a projection of a races.race_entries row)."""
    id: int                            # negative for a Race-tagged activity with no plan row
    name: str
    race_date: str                     # ISO date
    distance_km: Optional[float]
    status: str                        # completed | dnf | planned
    result_time_s: Optional[int]
    result_pace: Optional[str]         # "M:SS/km"
    target_time_s: Optional[int]
    target_pace: Optional[str]         # "M:SS/km"
    activity_id: Optional[int]
    from_activity: bool                # synthesized from a Race/Parkrun-tagged run


@dataclass
class BlockWeek:
    """One calendar week (Monday-aligned) of a block."""
    offset: int                        # weeks relative to race week: 0 = race week, -1 = the week before
    week_start: str                    # ISO Monday
    km: float
    runs: int
    longest_km: float                  # 0.0 with no runs


@dataclass
class RaceBlock:
    """One race's training block with its week-by-week shape and summary."""
    race: BlockRace
    block_start: str                   # ISO Monday
    block_end: str                     # ISO date, inclusive
    in_progress: bool                  # the race is today or ahead
    weeks: list                        # list[BlockWeek], oldest first
    total_km: float
    runs: int
    avg_week_km: float                 # total_km / number of week entries
    peak_week: Optional[BlockWeek]     # on a tie the later week
    longest_run: Optional[ReadinessRun]
    long_run_km: Optional[float]       # the class's long-run threshold
    long_runs: int                     # runs at or above long_run_km (exactly the threshold counts)
    steady_runs: int                   # runs training_trends.m_per_beat accepts
    median_m_per_beat: Optional[float]
    median_steady_pace_s_per_km: Optional[int]
    median_steady_hr: Optional[int]


@dataclass
class BlockComparison:
    """Every block of one race class, oldest race first."""
    as_of: str
    race_class: str
    block_weeks: int
    long_run_km: float
    blocks: list = field(default_factory=list)   # list[RaceBlock]
    heuristic: bool = True


def _pace(time_s: Optional[int], distance_km: Optional[float]) -> Optional[str]:
    return seconds_to_pace(time_s / distance_km) if time_s and distance_km else None


def _block_race(e) -> BlockRace:
    return BlockRace(
        id=e.id, name=(e.name or "").strip(), race_date=e.race_date.isoformat(),
        distance_km=e.distance_km, status=e.status, result_time_s=e.result_time_s,
        result_pace=_pace(e.result_time_s, e.distance_km),
        target_time_s=e.target_time_s, target_pace=_pace(e.target_time_s, e.distance_km),
        activity_id=e.activity_id, from_activity=bool(getattr(e, "from_activity", False)),
    )


def _median_or_none(values: list):
    return statistics.median(values) if values else None


def _build_block(db: Session, e, cls: RaceClass, block_weeks: int, block_start: date,
                 as_of: date) -> RaceBlock:
    in_progress = e.race_date >= as_of
    day_before = e.race_date - timedelta(days=1)
    block_end = min(as_of, day_before) if in_progress else day_before

    runs = []
    if block_start <= block_end:
        runs = [r for r in activities_svc.unified_activities(db, date_from=block_start, date_to=block_end)
                if r.distance_km]

    # One entry per calendar week from block_start through block_end's week.
    weeks: list[BlockWeek] = []
    if block_start <= block_end:
        end_monday = block_end - timedelta(days=block_end.weekday())
        n_weeks = (end_monday - block_start).days // 7 + 1
        for i in range(n_weeks):
            ws = block_start + timedelta(weeks=i)
            wr = [r for r in runs if ws <= r.date < ws + timedelta(days=7)]
            weeks.append(BlockWeek(
                offset=i - (block_weeks - 1), week_start=ws.isoformat(),
                km=round(sum(r.distance_km for r in wr), 1), runs=len(wr),
                longest_km=round(max((r.distance_km for r in wr), default=0.0), 1),
            ))

    total_km = round(sum(r.distance_km for r in runs), 1)
    # max() keeps the first maximum, so scan newest-first: a tie picks the later week.
    peak = max(reversed(weeks), key=lambda w: w.km) if runs else None

    steady = [(r, mpb) for r in runs if (mpb := training_trends.m_per_beat(r)) is not None]
    # Pace uses the same effective moving time m_per_beat does. That helper is
    # private to activities.py; importing it across modules is the established
    # pattern (training_trends, strava_stats, insights do the same).
    paces = [activities_svc._effective_moving_s(r) / r.distance_km for r, _ in steady]
    med_pace = _median_or_none(paces)
    med_hr = _median_or_none([r.avg_hr for r, _ in steady])
    med_mpb = _median_or_none([m for _, m in steady])

    return RaceBlock(
        race=_block_race(e), block_start=block_start.isoformat(), block_end=block_end.isoformat(),
        in_progress=in_progress, weeks=weeks, total_km=total_km, runs=len(runs),
        avg_week_km=round(total_km / len(weeks), 1) if weeks else 0.0,
        peak_week=peak,
        longest_run=_run(max(runs, key=lambda r: r.distance_km)) if runs else None,
        long_run_km=cls.long_run_km,
        long_runs=sum(1 for r in runs if r.distance_km >= cls.long_run_km),
        steady_runs=len(steady),
        median_m_per_beat=round(med_mpb, 3) if med_mpb is not None else None,
        median_steady_pace_s_per_km=round(med_pace) if med_pace is not None else None,
        median_steady_hr=round(med_hr) if med_hr is not None else None,
    )


def _class_entries(db: Session, cls: RaceClass, as_of: date) -> list:
    """Race entries of one class that belong in a block comparison, sorted by
    (date, id): done before `as_of` (completed or dnf, incl. Race-tagged runs
    with no plan row) or still planned on or after it. Read-only."""
    kept = []
    for e in races_svc.race_entries(db, as_of):
        rc = race_class_for(e.distance_km)
        if rc is None or rc.name != cls.name:
            continue
        done = e.race_date < as_of and e.status in races_svc.DONE_STATUSES
        upcoming = e.status == "planned" and e.race_date >= as_of
        if done or upcoming:
            kept.append(e)
    kept.sort(key=lambda e: (e.race_date, e.id))
    return kept


def block_comparison(
    db: Session, *, race_class: str = "marathon", as_of: Optional[date] = None,
) -> BlockComparison:
    """
    Side-by-side training blocks for every race of one class (R10.2).

    Block: the same definition as `race_readiness` (`block_window`) —
    `block_weeks` calendar weeks, Monday-aligned, ending with race week — read
    up to the day BEFORE race day (race-day running isn't training for it).
    Blocks of nearby races may overlap; a run then appears in both.

    Races: `races.race_entries` (read-only — no prune, nothing is written),
    keeping races of `race_class` that are either done before `as_of`
    (completed or dnf, including Race/Parkrun-tagged runs with no plan row) or
    still planned on or after `as_of` (an in-progress or future block, cut at
    `as_of`). Skipped races and past plans that never happened are excluded.
    A block that hasn't started is listed with empty weeks and zero totals.

    Heuristic: the long-run and steady-run rules are the readiness thresholds
    and training_trends' steady filter, not a physiological model.

    Raises ValueError if `race_class` isn't a RACE_CLASSES name.
    """
    cls = next((c for c in RACE_CLASSES if c.name == race_class), None)
    if cls is None:
        raise ValueError(f"Unknown race_class {race_class!r}; valid: "
                         + ", ".join(c.name for c in RACE_CLASSES))
    as_of = as_of or toronto_today()

    kept = _class_entries(db, cls, as_of)

    # Whole-table pass: one unified_activities read per block, filtered in Python
    # — fine at personal scale (~1k runs, a handful of races).
    blocks = []
    for e in kept:
        _, block_weeks, block_start = block_window(e.race_date, e.distance_km)
        blocks.append(_build_block(db, e, cls, block_weeks, block_start, as_of))

    return BlockComparison(as_of=as_of.isoformat(), race_class=cls.name, block_weeks=cls.block_weeks,
                           long_run_km=cls.long_run_km, blocks=blocks)
