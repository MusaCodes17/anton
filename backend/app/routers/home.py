"""
Home API (§4 Phase 4).

A single aggregate endpoint behind the rebuilt Home screen — four attention
modules (training pulse, shoe alerts, top deals, activity strip) in one round
trip. Thin adapter over `app.services.home`; all computation lives there so the
web UI, MCP, and future mobile client render identical numbers.
"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import home as home_svc

router = APIRouter(prefix="/home", tags=["home"])


class ShoeBrief(BaseModel):
    id: int
    brand: str
    model: str
    nickname: Optional[str] = None


class LastRunResponse(BaseModel):
    date: str
    distance_km: float
    source: str
    avg_pace: Optional[str] = None
    avg_hr: Optional[int] = None
    name: Optional[str] = None
    shoe: Optional[ShoeBrief] = None


class TrainingPulseResponse(BaseModel):
    this_week_km: float
    last_week_km: float
    delta_km: float
    last_run: Optional[LastRunResponse] = None


class ShoeAlertResponse(BaseModel):
    id: int
    brand: str
    model: str
    nickname: Optional[str] = None
    current_mileage: float
    mileage_limit: float
    pct: float
    replacement_deals: int


class TopDealResponse(BaseModel):
    id: int
    brand: str
    model: str
    retailer: str
    current_price: float
    savings_percent: float
    savings_amount: float
    product_url: str
    msrp: Optional[float] = None
    image_url: Optional[str] = None
    colorway: Optional[str] = None


class ActivityStripResponse(BaseModel):
    last_coros_sync_at: Optional[datetime] = None
    last_scrape_at: Optional[datetime] = None
    newest_deal_at: Optional[datetime] = None
    newest_deal_label: Optional[str] = None


class HomeResponse(BaseModel):
    training_pulse: TrainingPulseResponse
    shoe_alerts: List[ShoeAlertResponse]
    top_deals: List[TopDealResponse]
    activity_strip: ActivityStripResponse


@router.get("", response_model=HomeResponse)
@router.get("/", response_model=HomeResponse)
def get_home(db: Session = Depends(get_db)):
    """Everything the launch screen needs, in one request."""
    summary = home_svc.home_summary(db)
    return HomeResponse(
        training_pulse=TrainingPulseResponse(
            this_week_km=summary.training_pulse.this_week_km,
            last_week_km=summary.training_pulse.last_week_km,
            delta_km=summary.training_pulse.delta_km,
            last_run=(
                LastRunResponse(**summary.training_pulse.last_run.__dict__)
                if summary.training_pulse.last_run else None
            ),
        ),
        shoe_alerts=[ShoeAlertResponse(**a.__dict__) for a in summary.shoe_alerts],
        top_deals=[TopDealResponse(**d.__dict__) for d in summary.top_deals],
        activity_strip=ActivityStripResponse(**summary.activity_strip.__dict__),
    )
