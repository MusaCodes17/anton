"""
Unified activity feed API (§3 Phase-3a) — a thin router over
app.services.activities. Powers the Training tab's activities list and any
future mobile equivalent; no union/aggregation logic lives here.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import activities as activities_svc
from app.utils.activity_tags import ACTIVITY_TAGS

router = APIRouter(prefix="/activities", tags=["activities"])


class ActivityShoe(BaseModel):
    id: int
    brand: str
    model: str
    nickname: Optional[str] = None


class ActivityResponse(BaseModel):
    date: date
    distance_km: float
    source: str
    moving_time_s: Optional[int] = None
    avg_pace: Optional[str] = None
    avg_hr: Optional[int] = None
    elevation_m: Optional[float] = None
    name: Optional[str] = None
    activity_tag: Optional[str] = None
    activity_id: Optional[int] = None
    shoe: Optional[ActivityShoe] = None
    strava_activity_id: Optional[int] = None
    shoe_run_id: Optional[int] = None


@router.get("/tags", response_model=List[str])
def get_activity_tags():
    """The controlled `activity_tag` vocabulary (R2.7 T1), served so the frontend
    keeps no independent copy. Ordered for display. See app/utils/activity_tags.py."""
    return list(ACTIVITY_TAGS)


@router.get("", response_model=List[ActivityResponse])
@router.get("/", response_model=List[ActivityResponse])
def get_activities(
    year: Optional[int] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    shoe_id: Optional[int] = None,
    min_distance_km: Optional[float] = Query(None, ge=0),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    The unioned run feed (imported Strava + live shoe_runs), newest first.
    Filter by year/month or an inclusive date_from..date_to range (R2.7 T4b),
    plus shoe and minimum distance; paginate with limit/offset. Fetch
    `limit + 1`-style "load more" by requesting the next offset — a short page
    means the end.
    """
    return activities_svc.unified_activities(
        db,
        year=year,
        month=month,
        date_from=date_from,
        date_to=date_to,
        shoe_id=shoe_id,
        min_distance_km=min_distance_km,
        limit=limit,
        offset=offset,
    )
