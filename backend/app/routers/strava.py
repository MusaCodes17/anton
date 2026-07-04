"""
API routes for imported Strava data status.

A tiny read-only surface so the Settings → Sync & Scraping page (and the
future mobile client) can show "N activities imported, last export <date>".
Since §3 Phase-5 the Strava archive lives as source='strava' rows in the
canonical `activities` table.
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Activity

router = APIRouter(prefix="/strava", tags=["strava"])


class StravaStatus(BaseModel):
    """Import health for the Strava bulk export."""
    activity_count: int          # total imported activities (all types)
    run_count: int               # subset with activity_type == "Run"
    latest_activity_date: Optional[date] = None  # most recent run_date in the export
    imported_at: Optional[datetime] = None           # when the export was last ingested

    class Config:
        from_attributes = True


@router.get("/status", response_model=StravaStatus)
def get_strava_status(db: Session = Depends(get_db)):
    """Return counts and the export/import dates for the imported Strava archive."""
    strava = Activity.source == "strava"
    activity_count = db.query(func.count(Activity.id)).filter(strava).scalar() or 0
    run_count = (
        db.query(func.count(Activity.id))
        .filter(strava, Activity.activity_type == "Run")
        .scalar()
        or 0
    )
    latest_activity_date = db.query(func.max(Activity.run_date)).filter(strava).scalar()
    imported_at = db.query(func.max(Activity.created_at)).filter(strava).scalar()

    return StravaStatus(
        activity_count=activity_count,
        run_count=run_count,
        latest_activity_date=latest_activity_date,
        imported_at=imported_at,
    )
