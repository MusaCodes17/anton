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

    # Soonest upcoming race with days_remaining ≥ 0 and not completed
    all_races = races_svc.list_races(db, today)
    upcoming = [
        r for r in all_races
        if r.days_remaining >= 0 and getattr(r, "status", None) != "completed"
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
STATUSES = (STATUS_MET, STATUS_NOT_MET, STATUS_INFO, STATUS_NA)


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
class ChecklistItem:
    key: str                          # weeks_to_go | peak_week | longest_run | long_runs | key_effort
    label: str
    status: str                       # one of STATUSES
    rule: Optional[str]               # the stated rule (or why it can't apply)
    value: Optional[float]            # the runner's number
    target: Optional[float]           # the rule's number, when there is one
    unit: str                         # weeks | km | runs | s/km (pace: lower is faster)


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
    heuristic: bool = True


def toronto_today() -> date:
    return datetime.now(_TZ).date()


def race_class_for(distance_km: Optional[float]) -> Optional[RaceClass]:
    """The class a race distance falls in; None when the race has no distance."""
    if not distance_km:
        return None
    return next(c for c in RACE_CLASSES if distance_km >= c.min_distance_km)


def _readiness_race(db: Session, as_of: date) -> Optional[PlannedRace]:
    """The race readiness is about: the soonest non-skipped race on or after
    `as_of`. A direct read, not races.list_races (which prunes stale plans — a
    write). A *completed* race still counts while `as_of` is before its date:
    that only happens when asking about the past ("was I ready for the Spring
    Half?"), and it was a planned race then. On race day a completed race is
    done, so it's left out."""
    return (
        db.query(PlannedRace)
        .filter(
            PlannedRace.race_date >= as_of,
            PlannedRace.status != "skipped",
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
      pace; not_met when slower or when there's no such effort; n/a with no
      target time.

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

    cls = race_class_for(race.distance_km)
    block_weeks = cls.block_weeks if cls else DEFAULT_BLOCK_WEEKS
    race_monday = race.race_date - timedelta(days=race.race_date.weekday())
    block_start = race_monday - timedelta(weeks=block_weeks - 1)
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

    out.checklist = _checklist(out, cls)
    return out


def _checklist(rd: RaceReadiness, cls: Optional[RaceClass]) -> list[ChecklistItem]:
    """The checklist rows, in reading order. Rules are stated in words so every
    surface (page, MCP, Son of Anton) explains a status the same way."""
    race = rd.race
    items = [ChecklistItem(
        key="weeks_to_go", label="Weeks to go", status=STATUS_INFO,
        rule=f"{race.days_to_race} days to race day", value=race.weeks_to_race, target=None, unit="weeks",
    )]

    not_started = None if rd.block_started else f"The {rd.block_weeks}-week block starts {rd.block_start}"
    no_class = "The race has no distance, so there's no distance-relative rule"

    if not rd.block_started:
        peak_rule = not_started
    elif rd.peak_week:
        peak_rule = (f"Biggest ISO week of the block ({rd.peak_week.period}); "
                     f"this week so far {rd.current_week.total_km:g} km")
    else:
        peak_rule = "No running in the block yet"
    items.append(ChecklistItem(
        key="peak_week", label="Peak week",
        status=STATUS_INFO if rd.block_started else STATUS_NA, rule=peak_rule,
        value=rd.peak_week.total_km if rd.peak_week else None, target=None, unit="km",
    ))

    def gate() -> Optional[tuple[str, str]]:
        """(n/a, why) when a block rule can't apply, else None."""
        if cls is None:
            return STATUS_NA, no_class
        if not rd.block_started:
            return STATUS_NA, not_started
        return None

    longest = rd.longest_run.distance_km if rd.longest_run else None
    status, rule = gate() or (
        STATUS_MET if (longest or 0) >= cls.longest_target_km else STATUS_NOT_MET,
        f"Longest run in the block at least {cls.longest_target_km:g} km",
    )
    items.append(ChecklistItem(
        key="longest_run", label="Longest run", status=status, rule=rule,
        value=longest, target=cls.longest_target_km if cls else None, unit="km",
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
    ))

    # Key effort: needs a class (which distance) and a target (which pace).
    effort = next((e for e in rd.recent_efforts if e.label == rd.key_effort), None)
    if cls is None:
        status, rule = STATUS_NA, no_class
    elif race.target_pace_s_per_km is None:
        status, rule = STATUS_NA, "No target time set, so there's no target pace to compare with"
    else:
        status = STATUS_MET if effort and effort.pace_s_per_km <= race.target_pace_s_per_km else STATUS_NOT_MET
        rule = (f"Best {cls.key_effort} effort since {rd.effort_window_start} "
                f"at or faster than target pace ({race.target_pace})")
    items.append(ChecklistItem(
        key="key_effort",
        label=f"Recent {cls.key_effort} effort vs. target pace" if cls else "Recent effort vs. target pace",
        status=status, rule=rule,
        value=effort.pace_s_per_km if effort else None,
        target=race.target_pace_s_per_km if cls else None, unit="s/km",
    ))
    return items
