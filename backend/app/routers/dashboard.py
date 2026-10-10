"""
Dashboard API — thin adapter over services/dashboard.py.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DashboardStats
from app.services import dashboard as dashboard_svc

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    return dashboard_svc.get_stats(db)
