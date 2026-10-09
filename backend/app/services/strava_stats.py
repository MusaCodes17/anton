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
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import ActivityBestEffort, ActivityEffortScan, PlannedRace
from app.services import activities as activities_svc
from app.services import rotation
from app.services.activities import UnifiedActivity, _effective_moving_s
from app.utils.activity_tags import RACE_RESULT_TAGS
from app.utils.best_efforts import EFFORT_DISTANCES

# Whole-run distance bands: (label, target_km, tolerance_km). Race PBs always
# use these; Best efforts use them only for runs with no scanned stream.
PB_BANDS = (
    ("5k", 5.0, 0.3),
    ("10k", 10.0, 0.5),
    ("half", 21.0975, 1.0),
    ("full", 42.195, 1.5),
)

ROLLING_WEEKS = 4   # Volume-chart trend line (R8.4.2): a month of weeks smooths one big or missed week


@dataclass
class PeriodSummary:
    period: str          # e.g. "2026-W27" or "2026-07"
    total_km: float
    run_count: int
    avg_pace: Optional[str]
    avg_hr: Optional[int]
    elevation_gain_m: float
    # Weekly only (R8.4.2): mean km of this calendar week and the 3 before it,
    # empty weeks counted as 0 — the Volume chart's trend line. None for months.
    rolling_4wk_km: Optional[float] = None


@dataclass
class PersonalBest:
    band: str
    target_km: float
    run_date: Optional[str]
    name: Optional[str]
    distance_km: float               # the effort's distance (the band's, for a segment)
    total_time_s: int                # elapsed time over that distance — the headline figure
    avg_pace: str                    # total_time_s / distance, so it matches the headline
    avg_hr: Optional[int]
    source: str
    shoe: Optional[dict]              # {id, brand, model, nickname} or None
    strava_activity_id: Optional[int]
    activity_id: Optional[int]        # canonical Activity id → the /activities/:id editor
    clock: str = "elapsed"            # "elapsed", or "moving" when the run has no elapsed time
    segment: bool = False             # a stretch inside the run (R8.2), not the whole run
    run_distance_km: Optional[float] = None  # the whole run's distance, when `segment`


@dataclass
class PersonalBestsResult:
    """The two record lists (R8.1, R8.2)."""
    race_pbs: list[PersonalBest]      # whole race results: Race/Parkrun-tagged or race-linked runs
    best_efforts: list[PersonalBest]  # fastest stretches inside any run (segments), 1k → full


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

    Weekly buckets also carry `rolling_4wk_km` (R8.4.2). It averages whole
    calendar weeks, so it reads 3 weeks before `date_from` and ignores the range
    cut: a range starting mid-week still gets that week's true rolling value.
    """
    if period not in ("weekly", "monthly"):
        raise ValueError("period must be 'weekly' or 'monthly'")

    lookback_from = date_from
    if period == "weekly" and date_from is not None:
        lookback_from = date_from - timedelta(days=date_from.weekday() + (ROLLING_WEEKS - 1) * 7)
    all_runs = activities_svc.unified_activities(db, date_from=lookback_from, date_to=date_to)
    runs = [r for r in all_runs if date_from is None or r.date >= date_from]

    week_km: dict[date, float] = {}   # Monday → km, over the lookback too
    if period == "weekly":
        for r in all_runs:
            monday = r.date - timedelta(days=r.date.weekday())
            week_km[monday] = week_km.get(monday, 0.0) + (r.distance_km or 0.0)
    monday_of: dict[str, date] = {}

    buckets: dict[str, dict] = {}
    for r in runs:
        key = _period_key(r.date, period)
        monday_of.setdefault(key, r.date - timedelta(days=r.date.weekday()))
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
            rolling_4wk_km=(
                round(sum(week_km.get(monday_of[key] - timedelta(weeks=k), 0.0)
                          for k in range(ROLLING_WEEKS)) / ROLLING_WEEKS, 1)
                if period == "weekly" else None
            ),
        ))
    return out


def _record_time_s(r: UnifiedActivity) -> tuple[Optional[float], str]:
    """The clock records are timed on (R8.1): elapsed time — gun time, what race
    results and Strava best efforts mean — falling back to moving time only for
    runs that have no elapsed time (some COROS rows). Returns (seconds, clock)."""
    if r.elapsed_time_s:
        return float(r.elapsed_time_s), "elapsed"
    return _effective_moving_s(r), "moving"


def _record(r: UnifiedActivity, *, band: str, target_km: float, time_s: float, clock: str,
            segment: bool) -> PersonalBest:
    """One record shaped for the boundary. A segment's distance is the band's,
    its pace comes from that distance, and it carries no HR (the run's average
    HR isn't the stretch's)."""
    dist_km = target_km if segment else r.distance_km
    return PersonalBest(
        band=band,
        target_km=target_km,
        run_date=r.date.isoformat() if r.date else None,
        name=r.name,
        distance_km=round(dist_km, 2),
        total_time_s=round(time_s),
        avg_pace=rotation.seconds_to_pace(time_s / dist_km),
        avg_hr=None if segment else r.avg_hr,
        source=r.source,
        shoe=(
            {"id": r.shoe.id, "brand": r.shoe.brand, "model": r.shoe.model, "nickname": r.shoe.nickname}
            if r.shoe else None
        ),
        strava_activity_id=r.strava_activity_id,
        activity_id=r.activity_id,
        clock=clock,
        segment=segment,
        run_distance_km=round(r.distance_km, 2) if segment else None,
    )


def _band_bests(runs: list[tuple[UnifiedActivity, float, str]]) -> list[PersonalBest]:
    """Fastest whole run per PB band (lowest total time)."""
    out = []
    for label, target, tol in PB_BANDS:
        in_band = [x for x in runs if abs(x[0].distance_km - target) <= tol]
        if not in_band:
            continue
        best, best_time_s, clock = min(in_band, key=lambda x: x[1])
        out.append(_record(best, band=label, target_km=target, time_s=best_time_s, clock=clock, segment=False))
    return out


def personal_bests(
    db: Session,
    *,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> PersonalBestsResult:
    """
    Records per distance, as two lists:

    - **Race PBs** (R8.1) — whole race results: runs tagged Race/Parkrun, or
      linked to a planned race (`planned_races.activity_id`, R8.3), banded by
      the run's distance (5k → full). Computed live, so re-tagging a race
      removes it on the next load.
    - **Best efforts** (R8.2) — the fastest stretch of any run at 1k, mile, 5k,
      10k, half and full, from `activity_best_efforts` (the 5k inside a 10k
      race counts). Every run counts, intervals included: a stretch is
      continuous running on the elapsed clock, so rests inside it count
      against it. A run with no scanned stream yet (manual entries, a COROS
      run awaiting its FIT) competes with its whole-run time in the 5k → full
      bands, so it isn't invisible.

    Everything is on elapsed time (see _record_time_s). Whole-table pass over
    the unioned history: acceptable at personal scale (~1k runs), as in
    training_summary.

    `date_from`/`date_to` (inclusive, R8.4.4) restrict the runs that compete —
    the race-readiness checklist asks "what are my *recent* bests?" under the
    exact same rules as the Records card, so the two can never disagree.
    """
    race_linked = {
        aid for (aid,) in db.query(PlannedRace.activity_id).filter(PlannedRace.activity_id.isnot(None))
    }
    scanned = {
        aid for (aid,) in db.query(ActivityEffortScan.activity_id).filter(ActivityEffortScan.status == "ok")
    }
    by_id: dict[int, UnifiedActivity] = {}
    races: list[tuple[UnifiedActivity, float, str]] = []
    unscanned: list[tuple[UnifiedActivity, float, str]] = []
    for r in activities_svc.unified_activities(db, date_from=date_from, date_to=date_to):
        if not r.distance_km:
            continue
        by_id[r.activity_id] = r
        total_s, clock = _record_time_s(r)
        if not total_s:
            continue
        if r.activity_tag in RACE_RESULT_TAGS or r.activity_id in race_linked:
            races.append((r, total_s, clock))
        if r.activity_id not in scanned:
            unscanned.append((r, total_s, clock))

    # Fastest segment per distance (only efforts of runs in the unioned history).
    seg_best: dict[str, tuple[int, int]] = {}  # label -> (elapsed_s, activity_id)
    for label, elapsed_s, aid in db.query(
        ActivityBestEffort.distance_label, ActivityBestEffort.elapsed_s, ActivityBestEffort.activity_id
    ):
        if aid in by_id and (label not in seg_best or elapsed_s < seg_best[label][0]):
            seg_best[label] = (elapsed_s, aid)
    whole_best = {b.band: b for b in _band_bests(unscanned)}

    best_efforts: list[PersonalBest] = []
    for label, metres in EFFORT_DISTANCES:
        candidates = []
        if label in seg_best:
            elapsed_s, aid = seg_best[label]
            candidates.append(_record(by_id[aid], band=label, target_km=metres / 1000,
                                      time_s=elapsed_s, clock="elapsed", segment=True))
        if label in whole_best:
            candidates.append(whole_best[label])
        if candidates:
            best_efforts.append(min(candidates, key=lambda b: b.total_time_s / b.distance_km))

    return PersonalBestsResult(race_pbs=_band_bests(races), best_efforts=best_efforts)
