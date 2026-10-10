"""Longitudinal analytics (R5.5) — thin adapter over app.services.insights."""
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.schemas.insights import RotationInsightsResponse, ShoeInsightsResponse
from app.services import insights

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/shoes/{owned_shoe_id}", response_model=ShoeInsightsResponse)
def get_shoe_insights(owned_shoe_id: int, db: Session = Depends(get_db)):
    """Steady-run performance, model comparison, wear curve and type wear for one pair."""
    try:
        return ShoeInsightsResponse(**asdict(insights.shoe_insights(db, owned_shoe_id)))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/rotation", response_model=RotationInsightsResponse)
def get_rotation_insights(db: Session = Depends(get_db)):
    """Per-model performance and retired-shoe wear by type across the rotation."""
    return RotationInsightsResponse(**asdict(insights.rotation_insights(db)))
