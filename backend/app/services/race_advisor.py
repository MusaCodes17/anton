"""
Race-block training advisor (R3.6).

Assembles the structured context a training-block advisor needs: next race
countdown, recent weekly volumes, rotation pipeline state, and the latest
fitness snapshot. Read-only — no invariants are touched.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

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
    fitness snapshot. All reads — no writes, no invariants touched.

    Args:
        db:         Active database session.
        today:      Reference date (defaults to date.today()). Injected in tests.
        weeks_back: Number of recent weekly buckets to include (default 12).
    """
    today = today or date.today()

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
                snap.captured_at.date().isoformat() if snap.captured_at else None
            ),
        )

    return RaceBlockContext(
        has_next_race=next_race is not None,
        next_race=next_race,
        recent_weeks=recent_weeks,
        avg_weekly_km=avg_km,
        pipeline=pipeline,
        has_fitness=fitness is not None,
        fitness=fitness,
    )
