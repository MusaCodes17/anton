"""
Read-only analytics over run history (§6, §3).

Pure query helpers behind the MCP tools get_training_summary /
get_personal_bests. As of Phase 3 these compute over the UNION of imported
Strava runs and live `shoe_runs` (via app.services.activities), not
`strava_activities` alone — so post-export COROS/manual runs are included and
the web UI, MCP, and mobile client all agree. Pace formatting to "M:SS/km"
happens here at the boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.services import activities as activities_svc
from app.services import rotation
from app.services.activities import UnifiedActivity, _effective_moving_s
from app.utils.activity_tags import pb_exclusion_reason

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
    run_date: Optional[str]
    name: Optional[str]
    distance_km: float
    total_time_s: int                # whole-activity time — the headline figure
    avg_pace: str
    avg_hr: Optional[int]
    source: str
    shoe: Optional[dict]              # {id, brand, model, nickname} or None
    strava_activity_id: Optional[int]


@dataclass
class PersonalBestsResult:
    """PB records plus transparency about what the eligibility filter dropped
    (R2.7 T3), so the UI can nudge the runner to tag excluded history."""
    records: list[PersonalBest]
    excluded_count: int
    excluded_reason: Optional[str]    # human summary when excluded_count > 0


def _period_key(d: date, period: str) -> str:
    if period == "weekly":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    # monthly (default)
    return f"{d.year}-{d.month:02d}"


def training_summary(
    db: Session,
    period: str = "monthly",
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[PeriodSummary]:
    """
    Aggregate the unioned run history by week or month, newest period first.
    Pace is a distance-weighted average via total moving time / total distance
    (moving time reconstructed from average pace for runs that lack it); HR is
    a simple mean over runs that recorded it.

    `date_from`/`date_to` (inclusive, R2.7 T4b) restrict the runs aggregated so
    the Training-tab summary card can honour the same date-range picker as the
    volume chart and activities list.
    """
    if period not in ("weekly", "monthly"):
        raise ValueError("period must be 'weekly' or 'monthly'")

    runs = activities_svc.unified_activities(db, date_from=date_from, date_to=date_to)

    buckets: dict[str, dict] = {}
    for r in runs:
        key = _period_key(r.date, period)
        b = buckets.setdefault(key, {"km": 0.0, "count": 0, "moving_s": 0.0, "hr_sum": 0, "hr_n": 0, "elev": 0.0})
        b["km"] += r.distance_km or 0.0
        b["count"] += 1
        moving_s = _effective_moving_s(r)
        if moving_s:
            b["moving_s"] += moving_s
        if r.avg_hr is not None:
            b["hr_sum"] += r.avg_hr
            b["hr_n"] += 1
        b["elev"] += r.elevation_m or 0.0

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


def personal_bests(db: Session) -> PersonalBestsResult:
    """
    Fastest whole-activity time within each distance band, across the unioned
    run history. The record is the run with the lowest total time in the band;
    the card shows that time as the headline, with average pace and HR beneath.
    These are whole-activity times, not true segment PBs — describe accordingly.
    Shoe attribution is included when the winning run is linked to an owned shoe.

    Eligibility (R2.7 T3): interval/track sessions are excluded (they'd fake a
    record at their rep distance), Race/Parkrun always count, and untagged
    stop-heavy runs (elapsed ≫ moving) are excluded via the ratio guard. The
    dropped count + a summary reason ride along so the UI can prompt tagging.
    """
    runs = []
    excluded_reasons: dict[str, int] = {}
    for r in activities_svc.unified_activities(db):
        if not r.distance_km or r.avg_pace_s_per_km is None:
            continue
        reason = pb_exclusion_reason(r.activity_tag, r.elapsed_time_s, r.moving_time_s)
        if reason is not None:
            excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
            continue
        total_s = _effective_moving_s(r)
        if total_s:
            runs.append((r, total_s))

    out = []
    for label, target, tol in PB_BANDS:
        in_band = [(r, t) for (r, t) in runs if abs(r.distance_km - target) <= tol]
        if not in_band:
            continue
        best, best_time_s = min(in_band, key=lambda rt: rt[1])
        out.append(PersonalBest(
            band=label,
            target_km=target,
            run_date=best.date.isoformat() if best.date else None,
            name=best.name,
            distance_km=round(best.distance_km, 2),
            total_time_s=round(best_time_s),
            avg_pace=rotation.seconds_to_pace(best.avg_pace_s_per_km),
            avg_hr=best.avg_hr,
            source=best.source,
            shoe=(
                {
                    "id": best.shoe.id,
                    "brand": best.shoe.brand,
                    "model": best.shoe.model,
                    "nickname": best.shoe.nickname,
                }
                if best.shoe
                else None
            ),
            strava_activity_id=best.strava_activity_id,
        ))

    excluded_count = sum(excluded_reasons.values())
    excluded_reason = None
    if excluded_count:
        # "3 interval/track session, 2 stop-heavy untagged run"
        excluded_reason = ", ".join(
            f"{n} {reason}" for reason, n in sorted(excluded_reasons.items())
        )
    return PersonalBestsResult(
        records=out,
        excluded_count=excluded_count,
        excluded_reason=excluded_reason,
    )
