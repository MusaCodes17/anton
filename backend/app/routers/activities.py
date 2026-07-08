"""
Unified activity feed API (§3 Phase-3a) — a thin router over
app.services.activities. Powers the Training tab's activities list and any
future mobile equivalent; no union/aggregation logic lives here.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.schemas import PlannedRaceResponse
from app.services import activities as activities_svc
from app.services import races as races_svc
from app.services import rotation
from app.utils.activity_tags import ACTIVITY_TAGS, is_valid_tag

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


class ActivityDetail(BaseModel):
    """Full field set for one activity (R2.7 T6). Superset of the list row."""
    id: int
    source: str
    name: Optional[str] = None
    description: Optional[str] = None
    run_date: Optional[str] = None
    distance_km: Optional[float] = None
    moving_time_s: Optional[int] = None
    elapsed_time_s: Optional[int] = None
    avg_pace: Optional[str] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    elevation_gain_m: Optional[float] = None
    avg_cadence: Optional[float] = None
    calories: Optional[float] = None
    training_load: Optional[float] = None
    training_focus: Optional[str] = None
    activity_tag: Optional[str] = None
    strava_activity_id: Optional[int] = None
    shoe: Optional[ActivityShoe] = None


class ActivityUpdate(BaseModel):
    """Partial edit of an activity (R2.7 T6): tag, name, description."""
    activity_tag: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


class ReassignShoe(BaseModel):
    shoe_id: int = Field(..., description="Owned shoe to attribute this run to.")


@router.get("/{activity_id}", response_model=ActivityDetail)
def get_activity(activity_id: int, db: Session = Depends(get_db)):
    """Full detail for one activity (the T6 detail view)."""
    try:
        return activities_svc.get_activity_detail(db, activity_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{activity_id}", response_model=ActivityDetail)
def patch_activity(activity_id: int, payload: ActivityUpdate, db: Session = Depends(get_db)):
    """Partial-edit tag / name / description. Only supplied fields change; a tag
    must be a member of the ACTIVITY_TAGS vocabulary (or null to clear)."""
    fields = payload.model_dump(exclude_unset=True)
    if "activity_tag" in fields and fields["activity_tag"] is not None and not is_valid_tag(fields["activity_tag"]):
        raise HTTPException(status_code=400, detail=f"Invalid activity_tag. Use one of: {', '.join(ACTIVITY_TAGS)}.")
    try:
        activities_svc.update_activity(db, activity_id, **fields)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return activities_svc.get_activity_detail(db, activity_id)


@router.post("/{activity_id}/reassign-shoe", response_model=ActivityDetail)
def reassign_shoe(activity_id: int, payload: ReassignShoe, db: Session = Depends(get_db)):
    """Move this run's shoe attribution to another owned shoe, adjusting both
    shoes' mileage ledgers (INV-1). Separate from PATCH — different write
    semantics (it touches the ShoeRun + two counters, not the Activity)."""
    try:
        rotation.reassign_attribution(db, activity_id, payload.shoe_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return activities_svc.get_activity_detail(db, activity_id)


@router.post("/{activity_id}/promote-to-race", response_model=PlannedRaceResponse, status_code=201)
def promote_to_race(activity_id: int, db: Session = Depends(get_db)):
    """Create a completed race row from this activity (R2.7 T6) — for logging a
    race you ran so it appears on the Races dashboard."""
    try:
        race = races_svc.create_completed_from_activity(db, activity_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return races_svc.race_to_dict(race)
