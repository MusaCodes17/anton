"""
Dashboard aggregate queries.

Extracted from routers/dashboard.py (fat adapter, 2026-07-10).
The /api/dashboard/* endpoints are legacy surfaces from the pre-redesign
era; SettingsSync.jsx uses /dashboard/stats; the other two endpoints are
available for tools that may need them.  routers/dashboard.py is now a
thin adapter over these functions.
"""
from __future__ import annotations

import logging

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models.models import Deal, PriceRecord, Retailer, Shoe
from app.models.schemas import DashboardStats

logger = logging.getLogger(__name__)


def get_stats(db: Session) -> DashboardStats:
    """Aggregate counts for the dashboard overview."""
    total_shoes = db.query(Shoe).count()
    active_shoes = db.query(Shoe).filter(Shoe.is_active == True).count()  # noqa: E712

    total_retailers = db.query(Retailer).count()
    active_retailers = db.query(Retailer).filter(Retailer.scraping_enabled == True).count()  # noqa: E712

    active_deals = db.query(Deal).filter(Deal.is_active == True).count()  # noqa: E712
    total_price_records = db.query(PriceRecord).count()

    last_scrape_record = (
        db.query(Retailer.last_scraped_at)
        .order_by(desc(Retailer.last_scraped_at))
        .first()
    )
    last_scrape = last_scrape_record[0] if last_scrape_record else None

    avg_savings = (
        db.query(func.avg(Deal.savings_amount))
        .filter(Deal.is_active == True)  # noqa: E712
        .scalar()
    )

    return DashboardStats(
        total_shoes=total_shoes,
        active_shoes=active_shoes,
        total_retailers=total_retailers,
        active_retailers=active_retailers,
        active_deals=active_deals,
        total_price_records=total_price_records,
        last_scrape=last_scrape,
        average_savings=float(avg_savings) if avg_savings else None,
    )


def get_recent_deals(db: Session, *, limit: int = 10) -> list[Deal]:
    """Most recently detected active deals."""
    return (
        db.query(Deal)
        .filter(Deal.is_active == True)  # noqa: E712
        .order_by(desc(Deal.detected_at))
        .limit(limit)
        .all()
    )


def get_best_deals(db: Session, *, limit: int = 10) -> list[Deal]:
    """Active deals ordered by savings percentage, best first."""
    return (
        db.query(Deal)
        .filter(Deal.is_active == True)  # noqa: E712
        .order_by(desc(Deal.savings_percent))
        .limit(limit)
        .all()
    )
