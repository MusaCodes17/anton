"""
Read-only analytics over imported Strava run history (§6).

Pure query helpers behind the MCP tools get_training_summary /
get_personal_bests. Runs only (activity_type == 'Run'). Pace is stored as
seconds-per-km; formatting to "M:SS/km" happens here at the boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import StravaActivity
from app.services import rotation

# Distance bands for personal bests: (label, target_km, tolerance_km).
# These are average-pace-for-the-whole-activity bests, NOT true segment PBs.
PB_BANDS = (
    ("5k", 5.0, 0.3),
    ("10k", 10.0, 0.5),
    ("half", 21.0975, 1.0),
    ("full", 42.195, 1.5),
)


@dataclass
class PeriodSummary:
    period: str          # e.g. "2026-W27" or "2026-07"
    total_km: float
    run_count: int
    avg_pace: Optional[str]
    avg_hr: Optional[int]
    elevation_gain_m: float


@dataclass
class PersonalBest:
    band: str
    target_km: float
    strava_activity_id: int
    run_date: Optional[str]
    name: Optional[str]
    distance_km: float
    avg_pace: str
    avg_hr: Optional[int]


def _period_key(activity: StravaActivity, period: str) -> Optional[str]:
    d = activity.run_date
    if d is None:
        return None
    if period == "weekly":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    # monthly (default)
    return f"{d.year}-{d.month:02d}"


def training_summary(db: Session, period: str = "monthly") -> list[PeriodSummary]:
    """
    Aggregate run history by week or month, newest period first. Pace is a
    distance-weighted average via total moving time / total distance; HR is a
    simple mean over runs that recorded it.
    """
    if period not in ("weekly", "monthly"):
        raise ValueError("period must be 'weekly' or 'monthly'")

    runs = (
        db.query(StravaActivity)
        .filter(StravaActivity.activity_type == "Run")
        .all()
    )

    buckets: dict[str, dict] = {}
    for r in runs:
        key = _period_key(r, period)
        if key is None:
            continue
        b = buckets.setdefault(key, {"km": 0.0, "count": 0, "moving_s": 0, "hr_sum": 0, "hr_n": 0, "elev": 0.0})
        b["km"] += r.distance_km or 0.0
        b["count"] += 1
        if r.moving_time_s and r.distance_km:
            b["moving_s"] += r.moving_time_s
        if r.avg_hr is not None:
            b["hr_sum"] += r.avg_hr
            b["hr_n"] += 1
        b["elev"] += r.elevation_gain_m or 0.0

    out = []
    for key in sorted(buckets, reverse=True):
        b = buckets[key]
        avg_pace = None
        if b["km"] > 0 and b["moving_s"] > 0:
            avg_pace = rotation.seconds_to_pace(b["moving_s"] / b["km"])
        avg_hr = round(b["hr_sum"] / b["hr_n"]) if b["hr_n"] else None
        out.append(PeriodSummary(
            period=key,
            total_km=round(b["km"], 2),
            run_count=b["count"],
            avg_pace=avg_pace,
            avg_hr=avg_hr,
            elevation_gain_m=round(b["elev"], 1),
        ))
    return out


def personal_bests(db: Session) -> list[PersonalBest]:
    """
    Fastest average pace within each distance band. These are whole-activity
    average-pace bests, not true segment PBs — name/describe accordingly.
    """
    runs = (
        db.query(StravaActivity)
        .filter(
            StravaActivity.activity_type == "Run",
            StravaActivity.avg_pace_s_per_km.isnot(None),
            StravaActivity.distance_km.isnot(None),
        )
        .all()
    )

    out = []
    for label, target, tol in PB_BANDS:
        in_band = [r for r in runs if abs(r.distance_km - target) <= tol]
        if not in_band:
            continue
        best = min(in_band, key=lambda r: r.avg_pace_s_per_km)
        out.append(PersonalBest(
            band=label,
            target_km=target,
            strava_activity_id=best.strava_activity_id,
            run_date=best.run_date.isoformat() if best.run_date else None,
            name=best.name,
            distance_km=round(best.distance_km, 2),
            avg_pace=rotation.seconds_to_pace(best.avg_pace_s_per_km),
            avg_hr=best.avg_hr,
        ))
    return out
