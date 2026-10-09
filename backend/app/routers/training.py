"""
API routes for imported Strava training analytics.

Thin router-level adapter over app.services.strava_stats — no aggregation
logic lives here; it only exposes the service's PeriodSummary results.
"""
from dataclasses import asdict
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import strava_stats, fitness as fitness_svc, training_trends
from app.utils.pace import seconds_to_pace

router = APIRouter(prefix="/training", tags=["training"])


class PeriodSummaryResponse(BaseModel):
    """One week or month bucket from strava_stats.training_summary."""
    period: str            # "2026-07" (monthly) or "2026-W27" (weekly)
    total_km: float
    run_count: int
    avg_pace: Optional[str] = None
    avg_hr: Optional[int] = None
    elevation_gain_m: float
    rolling_4wk_km: Optional[float] = None   # weekly only (R8.4.2)

    class Config:
        from_attributes = True


class RecordShoe(BaseModel):
    id: int
    brand: str
    model: str
    nickname: Optional[str] = None


class PersonalBestResponse(BaseModel):
    """One distance record from strava_stats.personal_bests: a whole race result
    (Race PBs) or the fastest stretch inside a run (Best efforts, `segment`)."""
    band: str              # "5k" | "10k" | "half" | "full"
    target_km: float
    run_date: Optional[str] = None
    name: Optional[str] = None
    distance_km: float     # the effort's distance (the band's, for a segment)
    total_time_s: int      # elapsed time over that distance — the headline figure
    avg_pace: str
    avg_hr: Optional[int] = None
    source: str
    shoe: Optional[RecordShoe] = None
    strava_activity_id: Optional[int] = None
    activity_id: Optional[int] = None      # canonical id → the activity detail/editor
    clock: str = "elapsed"                 # "moving" when the run has no elapsed time
    segment: bool = False                  # a stretch inside the run (R8.2)
    run_distance_km: Optional[float] = None  # the whole run's distance, when segment

    class Config:
        from_attributes = True


class PersonalBestsResponse(BaseModel):
    """Race PBs (R8.1) and best efforts (R8.2)."""
    race_pbs: List[PersonalBestResponse]
    best_efforts: List[PersonalBestResponse]

    class Config:
        from_attributes = True


@router.get("/summary", response_model=List[PeriodSummaryResponse])
def get_training_summary(
    period: str = Query("monthly", pattern="^(monthly|weekly)$"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Aggregated run volume by month or week (union of Strava + shoe_runs),
    newest period first. Optional inclusive date_from..date_to range (R2.7 T4b)."""
    return strava_stats.training_summary(db, period=period, date_from=date_from, date_to=date_to)


class FitnessResponse(BaseModel):
    """The most recent COROS fitness snapshot (R2.7 T5), or an empty envelope
    when none has been recorded. threshold_pace is formatted at the boundary."""
    has_data: bool = False
    captured_at: Optional[str] = None
    vo2max: Optional[float] = None
    threshold_pace_s_per_km: Optional[int] = None
    threshold_pace: Optional[str] = None            # "M:SS/km" presentation
    race_predictions: Optional[dict] = None          # {"5.0": 1234, ...}
    running_level: Optional[float] = None            # COROS running level score (F3)


@router.get("/fitness", response_model=FitnessResponse)
def get_fitness(db: Session = Depends(get_db)):
    """The latest athlete fitness snapshot (VO2 max, threshold pace, race
    predictions). Empty envelope (has_data=False) when nothing recorded yet —
    absence is not an error (graceful degradation)."""
    snap = fitness_svc.latest(db)
    if snap is None:
        return FitnessResponse(has_data=False)
    return FitnessResponse(
        has_data=True,
        captured_at=snap.captured_at.isoformat() if snap.captured_at else None,
        vo2max=snap.vo2max,
        threshold_pace_s_per_km=snap.threshold_pace_s_per_km,
        threshold_pace=seconds_to_pace(snap.threshold_pace_s_per_km) if snap.threshold_pace_s_per_km else None,
        race_predictions=snap.race_predictions,
        running_level=snap.running_level,
    )


@router.get("/records", response_model=PersonalBestsResponse)
def get_training_records(db: Session = Depends(get_db)):
    """Records as two lists: Race PBs (whole Race/Parkrun-tagged or race-linked
    runs, 5k → full) and Best efforts (the fastest stretch inside any run, 1k →
    full, R8.2). All on elapsed time."""
    return strava_stats.personal_bests(db)


class TaperRaceResponse(BaseModel):
    name: str
    race_date: str
    days_to_race: int


class LoadTrendResponse(BaseModel):
    """"Building or holding?" (R8.4.2): last 7 days vs. the prior 28 days'
    average week. A heuristic — the thresholds ride along so the UI can say so."""
    as_of: str
    verdict: str                 # building | holding | easing | taper | no_baseline
    ratio: Optional[float] = None
    last7_km: float
    last7_runs: int
    last7_longest_km: float
    prior_avg_week_km: float
    prior_longest_km: float
    taper_race: Optional[TaperRaceResponse] = None
    building_above: float
    easing_below: float
    heuristic: bool = True


class EfficiencyMonthResponse(BaseModel):
    month: str                           # "2026-07"
    steady_runs: int
    m_per_beat: Optional[float] = None   # None below min_month_runs


class EffortPointResponse(BaseModel):
    time_s: int
    pace_s_per_km: int
    distance_km: float
    run_date: Optional[str] = None
    name: Optional[str] = None
    activity_id: Optional[int] = None
    segment: bool


class RollingBestResponse(BaseModel):
    label: str                           # "5k" | "10k"
    target_km: float
    recent: Optional[EffortPointResponse] = None     # best in the last 90 days
    all_time: Optional[EffortPointResponse] = None
    pct_off_all_time: Optional[float] = None         # pace, recent vs. all-time


class FitnessPointResponse(BaseModel):
    captured_date: str
    vo2max: Optional[float] = None
    threshold_pace_s_per_km: Optional[int] = None
    running_level: Optional[float] = None


class FormTrendResponse(BaseModel):
    """"What's my form now?" (R8.4.3): steady-run efficiency (m per heartbeat),
    90-day vs. all-time best 5k/10k, and the COROS fitness line. A heuristic —
    the thresholds and minimums ride along so the UI can say so."""
    as_of: str
    verdict: str                 # improving | steady | slipping | not_enough_data
    change_pct: Optional[float] = None
    recent_m_per_beat: Optional[float] = None
    recent_steady_runs: int
    baseline_m_per_beat: Optional[float] = None
    baseline_steady_runs: int
    months: List[EfficiencyMonthResponse]
    best_efforts: List[RollingBestResponse]
    fitness: List[FitnessPointResponse]
    recent_days: int
    baseline_days: int
    min_steady_runs: int
    min_month_runs: int
    improving_above_pct: float
    slipping_below_pct: float
    heuristic: bool = True


class TrendsResponse(BaseModel):
    """The Training page's "Now" answers (R8.4): load (R8.4.2) and form (R8.4.3)."""
    load: LoadTrendResponse
    form: FormTrendResponse


@router.get("/trends", response_model=TrendsResponse)
def get_training_trends(as_of: Optional[date] = None, db: Session = Depends(get_db)):
    """Trend verdicts for the Training page; `as_of` defaults to today (Toronto)."""
    return TrendsResponse(
        load=asdict(training_trends.load_trend(db, as_of=as_of)),
        form=asdict(training_trends.form_trend(db, as_of=as_of)),
    )
