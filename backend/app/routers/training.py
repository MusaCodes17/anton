"""
API routes for imported Strava training analytics.

Thin router-level adapter over app.services.strava_stats — no aggregation
logic lives here; it only exposes the service's PeriodSummary results.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import strava_stats

router = APIRouter(prefix="/training", tags=["training"])


class PeriodSummaryResponse(BaseModel):
    """One week or month bucket from strava_stats.training_summary."""
    period: str            # "2026-07" (monthly) or "2026-W27" (weekly)
    total_km: float
    run_count: int
    avg_pace: Optional[str] = None
    avg_hr: Optional[int] = None
    elevation_gain_m: float

    class Config:
        from_attributes = True


class RecordShoe(BaseModel):
    id: int
    brand: str
    model: str
    nickname: Optional[str] = None


class PersonalBestResponse(BaseModel):
    """One distance-band record from strava_stats.personal_bests. Whole-activity
    average-pace best, not a segment PB."""
    band: str              # "5k" | "10k" | "half" | "full"
    target_km: float
    run_date: Optional[str] = None
    name: Optional[str] = None
    distance_km: float
    total_time_s: int      # whole-activity time — the headline figure
    avg_pace: str
    avg_hr: Optional[int] = None
    source: str
    shoe: Optional[RecordShoe] = None
    strava_activity_id: Optional[int] = None

    class Config:
        from_attributes = True


class PersonalBestsResponse(BaseModel):
    """The records plus what the eligibility filter dropped (R2.7 T3)."""
    records: List[PersonalBestResponse]
    excluded_count: int = 0
    excluded_reason: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/summary", response_model=List[PeriodSummaryResponse])
def get_training_summary(
    period: str = Query("monthly", pattern="^(monthly|weekly)$"),
    db: Session = Depends(get_db),
):
    """Aggregated run volume by month or week (union of Strava + shoe_runs),
    newest period first."""
    return strava_stats.training_summary(db, period=period)


@router.get("/records", response_model=PersonalBestsResponse)
def get_training_records(db: Session = Depends(get_db)):
    """Fastest average pace at each distance band, over the unioned run history.
    These are whole-activity average-pace bests, not segment PBs. Interval/track
    and stop-heavy untagged runs are excluded (R2.7 T3); the dropped count rides
    along so the UI can prompt the runner to tag history."""
    return strava_stats.personal_bests(db)
