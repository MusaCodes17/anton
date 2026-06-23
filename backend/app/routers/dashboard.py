"""
API routes for dashboard statistics
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models import Shoe, Retailer, PriceRecord, Deal, DashboardStats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Get dashboard statistics overview
    """
    # Count total and active shoes
    total_shoes = db.query(Shoe).count()
    active_shoes = db.query(Shoe).filter(Shoe.is_active == True).count()
    
    # Count total and active retailers
    total_retailers = db.query(Retailer).count()
    active_retailers = db.query(Retailer).filter(Retailer.is_active == True).count()
    
    # Count active deals
    active_deals = db.query(Deal).filter(Deal.is_active == True).count()
    
    # Count total price records
    total_price_records = db.query(PriceRecord).count()
    
    # Get last scrape time
    last_scrape_record = db.query(Retailer.last_scraped_at)\
        .order_by(desc(Retailer.last_scraped_at))\
        .first()
    last_scrape = last_scrape_record[0] if last_scrape_record else None
    
    # Calculate average savings from active deals
    avg_savings = db.query(func.avg(Deal.savings_amount))\
        .filter(Deal.is_active == True)\
        .scalar()
    
    return DashboardStats(
        total_shoes=total_shoes,
        active_shoes=active_shoes,
        total_retailers=total_retailers,
        active_retailers=active_retailers,
        active_deals=active_deals,
        total_price_records=total_price_records,
        last_scrape=last_scrape,
        average_savings=float(avg_savings) if avg_savings else None
    )


@router.get("/recent-deals")
def get_recent_deals(limit: int = 10, db: Session = Depends(get_db)):
    """
    Get most recent deals detected
    """
    deals = db.query(Deal)\
        .filter(Deal.is_active == True)\
        .order_by(desc(Deal.detected_at))\
        .limit(limit)\
        .all()
    
    return [{
        "id": deal.id,
        "shoe": {
            "brand": deal.shoe.brand,
            "model": deal.shoe.model,
            "msrp": deal.shoe.msrp
        },
        "retailer": deal.retailer.name,
        "current_price": deal.current_price,
        "savings_percent": deal.savings_percent,
        "product_url": deal.product_url,
        "sizes_available": deal.sizes_available,
        "image_url": deal.image_url,
        "colorway": deal.colorway,
        "detected_at": deal.detected_at
    } for deal in deals]


@router.get("/best-deals")
def get_best_deals(limit: int = 10, db: Session = Depends(get_db)):
    """
    Get best deals by savings percentage
    """
    deals = db.query(Deal)\
        .filter(Deal.is_active == True)\
        .order_by(desc(Deal.savings_percent))\
        .limit(limit)\
        .all()
    
    return [{
        "id": deal.id,
        "shoe": {
            "brand": deal.shoe.brand,
            "model": deal.shoe.model,
            "msrp": deal.shoe.msrp
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
        "detected_at": deal.detected_at
    } for deal in deals]
