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

from app.models.models import PlannedRace
from app.services import activities as activities_svc
from app.services import rotation
from app.services.activities import UnifiedActivity, _effective_moving_s
from app.utils.activity_tags import RACE_RESULT_TAGS, pb_exclusion_reason

# Distance bands for personal bests: (label, target_km, tolerance_km).
# These are whole-activity bests, NOT segments inside a longer run (R8.2).
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
    total_time_s: int                # whole-activity elapsed time — the headline figure
    avg_pace: str                    # total_time_s / distance, so it matches the headline
    avg_hr: Optional[int]
    source: str
    shoe: Optional[dict]              # {id, brand, model, nickname} or None
    strava_activity_id: Optional[int]
    activity_id: Optional[int]        # canonical Activity id → the /activities/:id editor
    clock: str = "elapsed"            # "elapsed", or "moving" when the run has no elapsed time


@dataclass
class PersonalBestsResult:
    """The two record lists (R8.1) plus what the best-efforts filter dropped
    (R2.7 T3), so the UI can explain exclusions."""
    race_pbs: list[PersonalBest]      # official results: Race/Parkrun-tagged or race-linked runs
    best_efforts: list[PersonalBest]  # fastest runs of any kind except Intervals/Track
    excluded_count: int               # runs kept out of best efforts
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


def _record_time_s(r: UnifiedActivity) -> tuple[Optional[float], str]:
    """The clock records are timed on (R8.1): elapsed time — gun time, what race
    results and Strava best efforts mean — falling back to moving time only for
    runs that have no elapsed time (some COROS rows). Returns (seconds, clock)."""
    if r.elapsed_time_s:
        return float(r.elapsed_time_s), "elapsed"
    return _effective_moving_s(r), "moving"


def _band_bests(runs: list[tuple[UnifiedActivity, float, str]]) -> list[PersonalBest]:
    """Fastest run per PB band (lowest total time), shaped for the boundary."""
    out = []
    for label, target, tol in PB_BANDS:
        in_band = [x for x in runs if abs(x[0].distance_km - target) <= tol]
        if not in_band:
            continue
        best, best_time_s, clock = min(in_band, key=lambda x: x[1])
        out.append(PersonalBest(
            band=label,
            target_km=target,
            run_date=best.date.isoformat() if best.date else None,
            name=best.name,
            distance_km=round(best.distance_km, 2),
            total_time_s=round(best_time_s),
            avg_pace=rotation.seconds_to_pace(best_time_s / best.distance_km),
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
            activity_id=best.activity_id,
            clock=clock,
        ))
    return out


def personal_bests(db: Session) -> PersonalBestsResult:
    """
    The fastest whole-activity time in each distance band, as two lists (R8.1):

    - **Race PBs** — official results: runs tagged Race/Parkrun, or linked to a
      planned race (`planned_races.activity_id`, R8.3). Records are computed
      live, so re-tagging a race to a training tag removes it on the next load.
    - **Best efforts** — any run except Intervals/Track (their rep distances
      would fake a record). Races count here too, so a best effort is never
      slower than the Race PB in its band.

    Both are timed on elapsed time (see _record_time_s), with pace derived from
    that same time. These are whole-activity times, not segments inside a longer
    run (that's R8.2) — describe accordingly. Whole-table pass over the unioned
    history: acceptable at personal scale (~1k runs), as in training_summary.
    """
    race_linked = {
        aid for (aid,) in db.query(PlannedRace.activity_id).filter(PlannedRace.activity_id.isnot(None))
    }
    races: list[tuple[UnifiedActivity, float, str]] = []
    efforts: list[tuple[UnifiedActivity, float, str]] = []
    excluded_reasons: dict[str, int] = {}
    for r in activities_svc.unified_activities(db):
        if not r.distance_km:
            continue
        total_s, clock = _record_time_s(r)
        if not total_s:
            continue
        if r.activity_tag in RACE_RESULT_TAGS or r.activity_id in race_linked:
            races.append((r, total_s, clock))
        reason = pb_exclusion_reason(r.activity_tag)
        if reason is not None:
            excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
            continue
        efforts.append((r, total_s, clock))

    excluded_count = sum(excluded_reasons.values())
    excluded_reason = None
    if excluded_count:
        # "3 interval/track session"
        excluded_reason = ", ".join(
            f"{n} {reason}" for reason, n in sorted(excluded_reasons.items())
        )
    return PersonalBestsResult(
        race_pbs=_band_bests(races),
        best_efforts=_band_bests(efforts),
        excluded_count=excluded_count,
        excluded_reason=excluded_reason,
    )
