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


@router.get("/recent-deals")
def get_recent_deals(limit: int = 10, db: Session = Depends(get_db)):
    deals = dashboard_svc.get_recent_deals(db, limit=limit)
    return [
        {
            "id": deal.id,
            "shoe": {
                "brand": deal.shoe.brand,
                "model": deal.shoe.model,
                "msrp": deal.shoe.msrp,
            },
            "retailer": deal.retailer.name,
            "current_price": deal.current_price,
            "savings_percent": deal.savings_percent,
            "product_url": deal.product_url,
            "sizes_available": deal.sizes_available,
            "image_url": deal.image_url,
            "colorway": deal.colorway,
            "detected_at": deal.detected_at,
        }
        for deal in deals
    ]


@router.get("/best-deals")
def get_best_deals(limit: int = 10, db: Session = Depends(get_db)):
    deals = dashboard_svc.get_best_deals(db, limit=limit)
    return [
        {
            "id": deal.id,
            "shoe": {
                "brand": deal.shoe.brand,
                "model": deal.shoe.model,
                "msrp": deal.shoe.msrp,
            },
            "retailer": deal.retailer.name,
            "current_price": deal.current_price,
            "target_price": deal.target_price,
            "savings_amount": deal.savings_amount,
            "savings_percent": deal.savings_percent,
            "product_url": deal.product_url,
            "sizes_available": deal.sizes_available,
            "image_url": deal.image_url,
            "colorway": deal.colorway,
            "detected_at": deal.detected_at,
        }
        for deal in deals
    ]
