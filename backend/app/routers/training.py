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


@router.get("/summary", response_model=List[PeriodSummaryResponse])
def get_training_summary(
    period: str = Query("monthly", pattern="^(monthly|weekly)$"),
    db: Session = Depends(get_db),
):
    """Aggregated run volume by month or week, newest period first."""
    return strava_stats.training_summary(db, period=period)
