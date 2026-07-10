"""
Weekly rotation digest service (R3.1).

Compiles the runner's weekly summary in one pass: volume vs last week,
per-shoe usage, retirement pipeline, notable runs, 100km checkpoints
crossed, and next-race countdown. Read-only — no invariants are touched.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import OwnedShoe, ShoeNote
from app.services import activities as activities_svc
from app.services import rotation as rotation_svc
from app.services import races as races_svc

# Tags that mark a run as notable in the weekly digest. Workout and Easy/Recovery
# are intentionally excluded — the digest highlights quality sessions, not volume.
NOTABLE_TAGS: frozenset[str] = frozenset({"Race", "Parkrun", "Intervals", "Tempo", "Long Run", "Track"})


@dataclass
class WeeklyShoeUsage:
    shoe_id: int
    brand: str
    model: str
    nickname: Optional[str]
    shoe_type: Optional[str]
    km_this_week: float
    run_count: int


@dataclass
class WeeklyNotableRun:
    run_date: str           # ISO date
    distance_km: float
    avg_pace: Optional[str]
    avg_hr: Optional[int]
    activity_tag: str
    name: Optional[str]
    shoe: Optional[str]     # "Brand Model" or "Brand Model (nickname)"


@dataclass
class WeeklyCheckpoint:
    shoe_id: int
    brand: str
    model: str
    checkpoint_km: int      # 100km boundary crossed (e.g. 400)
    triggered_at: str       # ISO date of the note


@dataclass
class WeeklyPipelineEntry:
    shoe_id: int
    brand: str
    model: str
    nickname: Optional[str]
    pct: float              # current_mileage / mileage_limit, 0..1+
    current_mileage: float
    mileage_limit: float
    replacement_deals: int


@dataclass
class NextRace:
    name: str
    race_date: str          # ISO date
    days_remaining: int
    weeks_remaining: int
    distance_km: Optional[float]
    target_pace: Optional[str]  # "M:SS/km" if a target time is set


@dataclass
class WeeklySummary:
    week_start: str                 # ISO date (Monday)
    week_end: str                   # ISO date (Sunday)
    this_week_km: float
    last_week_km: float
    delta_km: float                 # this - last (negative = lower volume week)
    per_shoe_usage: list            # list[WeeklyShoeUsage], km-descending
    pipeline: list                  # list[WeeklyPipelineEntry], pct-descending
    notable_runs: list              # list[WeeklyNotableRun], newest-first
    checkpoints_this_week: list     # list[WeeklyCheckpoint]
    next_race: Optional[NextRace]   # soonest upcoming race (days_remaining ≥ 0)


def weekly_summary(db: Session, today: Optional[date] = None) -> WeeklySummary:
    """
    Compile the runner's weekly rotation digest.

    ISO-week (Monday–Sunday) anchored. Volume totals cover every Run-type
    activity in `activities` whether or not it has a shoe attribution.
    Per-shoe usage counts only attributed runs. Pipeline reflects the current
    rotation state (all active shoes ≥ 75% of their limit), not just changes
    this week — the full context is more useful than a delta the runner would
    have to reconstruct anyway.

    Args:
        db:    Active database session.
        today: Reference date for the week boundary (defaults to date.today()).
               Injected in tests so the suite is clock-independent.
    """
    today = today or date.today()
    this_start = today - timedelta(days=today.weekday())   # Monday of current ISO week
    this_end = this_start + timedelta(days=6)              # Sunday
    last_start = this_start - timedelta(days=7)
    last_end = this_start - timedelta(days=1)

    this_runs = activities_svc.unified_activities(db, date_from=this_start, date_to=this_end)
    last_runs = activities_svc.unified_activities(db, date_from=last_start, date_to=last_end)

    this_km = round(sum(r.distance_km for r in this_runs), 2)
    last_km = round(sum(r.distance_km for r in last_runs), 2)

    # Per-shoe usage: group attributed runs by shoe, km-descending
    usage_map: dict[int, WeeklyShoeUsage] = {}
    for r in this_runs:
        if r.shoe is None:
            continue
        sid = r.shoe.id
        if sid not in usage_map:
            usage_map[sid] = WeeklyShoeUsage(
                shoe_id=sid,
                brand=r.shoe.brand,
                model=r.shoe.model,
                nickname=r.shoe.nickname,
                shoe_type=None,   # enriched below
                km_this_week=0.0,
                run_count=0,
            )
        u = usage_map[sid]
        u.km_this_week = round(u.km_this_week + r.distance_km, 2)
        u.run_count += 1

    # Enrich shoe_type with a single OwnedShoe query (tiny result set at personal scale)
    if usage_map:
        for os in db.query(OwnedShoe).filter(OwnedShoe.id.in_(usage_map.keys())).all():
            if os.id in usage_map:
                usage_map[os.id].shoe_type = os.shoe_type

    per_shoe_usage = sorted(usage_map.values(), key=lambda u: u.km_this_week, reverse=True)

    # Notable runs (Race / Parkrun / Intervals / Tempo / Long Run / Track)
    # this_runs is newest-first from unified_activities so no extra sort needed
    notable_runs = [
        WeeklyNotableRun(
            run_date=r.date.isoformat(),
            distance_km=r.distance_km,
            avg_pace=r.avg_pace,
            avg_hr=r.avg_hr,
            activity_tag=r.activity_tag,
            name=r.name,
            shoe=(
                f"{r.shoe.brand} {r.shoe.model}"
                + (f" ({r.shoe.nickname})" if r.shoe.nickname else "")
                if r.shoe else None
            ),
        )
        for r in this_runs
        if r.activity_tag in NOTABLE_TAGS
    ]

    # Retirement pipeline — full current state, pct-descending
    pipeline = [
        WeeklyPipelineEntry(
            shoe_id=e.shoe.id,
            brand=e.shoe.brand,
            model=e.shoe.model,
            nickname=e.shoe.nickname,
            pct=e.pct,
            current_mileage=e.current_mileage,
            mileage_limit=e.mileage_limit,
            replacement_deals=e.replacement_deals,
        )
        for e in rotation_svc.retirement_pipeline(db)
    ]

    # 100km checkpoints triggered this ISO week.
    # Upper bound is exclusive (< Monday of next week) to avoid microsecond edge cases.
    week_start_dt = datetime.combine(this_start, datetime.min.time())
    week_after_dt = datetime.combine(this_end + timedelta(days=1), datetime.min.time())
    checkpoint_rows = (
        db.query(ShoeNote, OwnedShoe)
        .join(OwnedShoe, OwnedShoe.id == ShoeNote.owned_shoe_id)
        .filter(
            ShoeNote.triggered_by == "checkpoint",
            ShoeNote.created_at >= week_start_dt,
            ShoeNote.created_at < week_after_dt,
        )
        .all()
    )
    checkpoints = [
        WeeklyCheckpoint(
            shoe_id=note.owned_shoe_id,
            brand=shoe.brand,
            model=shoe.model,
            checkpoint_km=round(note.mileage_at_note) if note.mileage_at_note else 0,
            triggered_at=note.created_at.date().isoformat() if note.created_at else "",
        )
        for note, shoe in checkpoint_rows
    ]

    # Soonest upcoming race with days_remaining ≥ 0 and status ≠ completed
    all_races = races_svc.list_races(db, today)
    upcoming = [
        r for r in all_races
        if r.days_remaining >= 0 and getattr(r, "status", None) != "completed"
    ]
    next_race: Optional[NextRace] = None
    if upcoming:
        r = min(upcoming, key=lambda x: x.days_remaining)
        next_race = NextRace(
            name=r.name,
            race_date=r.race_date.isoformat() if hasattr(r.race_date, "isoformat") else str(r.race_date),
            days_remaining=r.days_remaining,
            weeks_remaining=r.weeks_remaining,
            distance_km=r.distance_km,
            target_pace=getattr(r, "target_pace", None),
        )

    return WeeklySummary(
        week_start=this_start.isoformat(),
        week_end=this_end.isoformat(),
        this_week_km=this_km,
        last_week_km=last_km,
        delta_km=round(this_km - last_km, 2),
        per_shoe_usage=per_shoe_usage,
        pipeline=pipeline,
        notable_runs=notable_runs,
        checkpoints_this_week=checkpoints,
        next_race=next_race,
    )
