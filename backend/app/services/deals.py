"""
Deal query service — the canonical home for deal-retrieval business logic.

Extracted from routers/deals.py (fat adapter) and from the inline queries
duplicated in mcp_server.py's get_deals / get_shoe_deals tools.  REST
endpoints and MCP tools are now thin adapters over these functions — one
source of truth for how deals are filtered and ordered (REST/MCP parity,
architecture principle §4.2).

Domain note: a deal exists iff price < shoe.msrp and msrp IS NOT NULL
(INV-6, B9-v2 qualification rule).  The 'is_active' flag reflects
DealStore's retirement/requalification logic — do not recompute it here.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.models import Deal, Shoe

logger = logging.getLogger(__name__)


def list_deals(
    db: Session,
    *,
    is_active: bool = True,
    min_savings_percent: Optional[float] = None,
    brand: Optional[str] = None,
    model: Optional[str] = None,
    shoe_type: Optional[str] = None,
    size: Optional[str] = None,
    skip: int = 0,
    limit: int = 500,
) -> list[Deal]:
    """
    Return deals ordered biggest-discount-first with optional filters.

    The default ``limit`` is deliberately high (500): the Deals page renders the
    full "On sale now" set in one round trip, and at single-user scale the active
    deal count sits in the low hundreds. A default of 100 silently truncated the
    page (the runner saw ~18 of ~45 shoes on sale). ``skip``/``limit`` remain
    functional for any paginated caller.

    brand/model/shoe_type filters are case-insensitive substring matches.
    size filtering happens in Python because SQLite has no portable JSON
    "contains" predicate — the query overfetches by 5× limit and filters in
    memory (same approach as the Deals page client-side size filter).
    """
    query = db.query(Deal)
    if is_active is not None:
        query = query.filter(Deal.is_active == is_active)
    if min_savings_percent is not None:
        query = query.filter(Deal.savings_percent >= min_savings_percent)
    needs_shoe_join = brand or model or shoe_type
    if needs_shoe_join:
        query = query.join(Deal.shoe)
        if brand:
            query = query.filter(Shoe.brand.ilike(f"%{brand}%"))
        if model:
            query = query.filter(Shoe.model.ilike(f"%{model}%"))
        if shoe_type:
            query = query.filter(Shoe.shoe_type == shoe_type)
    query = query.order_by(desc(Deal.savings_percent))

    if size:
        deals = [
            d for d in query.limit(limit * 5).all()
            if size in (d.sizes_available or [])
        ][:limit]
    else:
        deals = query.offset(skip).limit(limit).all()

    return deals


def get_deal(db: Session, deal_id: int) -> Deal | None:
    """Return a single deal by primary key, or None if not found."""
    return db.query(Deal).filter(Deal.id == deal_id).first()


def deactivate_deal(db: Session, deal_id: int) -> Deal:
    """
    Mark a deal inactive (e.g. purchased or expired by the user).

    Raises:
        LookupError: if deal_id does not exist.
    """
    deal = get_deal(db, deal_id)
    if not deal:
        raise LookupError(f"Deal {deal_id} not found")
    deal.is_active = False
    db.commit()
    db.refresh(deal)
    return deal


def get_deals_for_shoe(
    db: Session,
    shoe_id: int,
    *,
    is_active: bool = True,
) -> list[Deal]:
    """All deals for a specific tracked shoe, biggest discount first."""
    query = db.query(Deal).filter(Deal.shoe_id == shoe_id)
    if is_active is not None:
        query = query.filter(Deal.is_active == is_active)
    return query.order_by(desc(Deal.savings_percent)).all()


def get_deals_for_retailer(
    db: Session,
    retailer_id: int,
    *,
    is_active: bool = True,
) -> list[Deal]:
    """All deals from a specific retailer, biggest discount first."""
    query = db.query(Deal).filter(Deal.retailer_id == retailer_id)
    if is_active is not None:
        query = query.filter(Deal.is_active == is_active)
    return query.order_by(desc(Deal.savings_percent)).all()
