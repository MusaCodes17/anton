"""
Deal query service — the canonical home for deal-retrieval business logic.

Extracted from routers/deals.py (fat adapter) and from the inline queries
duplicated in mcp_server/deals.py's get_deals / get_shoe_deals tools.  REST
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

from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from app.models.models import Deal, Retailer, ScrapeRun, Shoe
from app.models.schemas.deals import PublicDeal, PublicDealsResponse, PublicPromoCode
from app.services import settings as settings_svc
from app.utils.shoe_sizes import parse_size_label, size_fit

logger = logging.getLogger(__name__)


def _deal_query(db: Session):
    """Deal query that eager-loads everything DealResponse serializes (shoe,
    retailer, retailer.promo_codes). Without it, ``Retailer.active_promo_codes``
    lazy-loads ``promo_codes`` once per deal row (N+1)."""
    return db.query(Deal).options(
        joinedload(Deal.shoe),
        joinedload(Deal.retailer).selectinload(Retailer.promo_codes),
    )


def attach_size_fit(db: Session, deals: list[Deal]) -> list[Deal]:
    """
    Stamp each deal with a transient ``size_fit`` ("in"/"out"/"unknown", or None
    when no size preference is set) — R6.3. Derived at the boundary, never
    stored (INV-7), and qualification stays size-agnostic: a deal is a deal,
    size is a per-runner view.
    """
    preferred = settings_svc.get_preferred_size(db)
    for d in deals:
        d.size_fit = size_fit(d.sizes_available, preferred)
    return deals


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
    query = _deal_query(db)
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
            if _has_size(d.sizes_available, size)
        ][:limit]
    else:
        deals = query.offset(skip).limit(limit).all()

    return attach_size_fit(db, deals)


def _has_size(sizes_available, size: str) -> bool:
    """Normalised membership ("9" matches "9.0" and "9 / 10.5"); falls back to
    the exact string for a label the parser can't read."""
    wanted = parse_size_label(size)
    for label in sizes_available or []:
        if label == size or (wanted is not None and parse_size_label(label) == wanted):
            return True
    return False


def get_deal(db: Session, deal_id: int) -> Deal | None:
    """Return a single deal by primary key, or None if not found."""
    deal = _deal_query(db).filter(Deal.id == deal_id).first()
    if deal:
        attach_size_fit(db, [deal])
    return deal


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
    query = _deal_query(db).filter(Deal.shoe_id == shoe_id)
    if is_active is not None:
        query = query.filter(Deal.is_active == is_active)
    return attach_size_fit(db, query.order_by(desc(Deal.savings_percent)).all())


def get_deals_for_retailer(
    db: Session,
    retailer_id: int,
    *,
    is_active: bool = True,
) -> list[Deal]:
    """All deals from a specific retailer, biggest discount first."""
    query = _deal_query(db).filter(Deal.retailer_id == retailer_id)
    if is_active is not None:
        query = query.filter(Deal.is_active == is_active)
    return attach_size_fit(db, query.order_by(desc(Deal.savings_percent)).all())


def list_public_deals(db: Session) -> PublicDealsResponse:
    """The public (logged-out) projection of active deals (R9.3).

    A thin projection over ``list_deals(db, is_active=True)`` (same
    biggest-discount-first ordering). Every field is copied explicitly so that
    personal data (notes, target_price, size_fit, ...) cannot leak by default.
    Performs no scrape or sync work: ``checked_at`` merely reads the latest
    successful ScrapeRun.finished_at (None if there is none).
    """
    deals = [
        PublicDeal(
            id=d.id,
            shoe_id=d.shoe_id,
            brand=d.shoe.brand,
            model=d.shoe.model,
            shoe_type=d.shoe.shoe_type,
            colorway=d.colorway,
            image_url=d.image_url,
            current_price=d.current_price,
            msrp=d.shoe.msrp,
            savings_amount=d.savings_amount,
            savings_percent=d.savings_percent,
            sizes_available=d.sizes_available,
            in_stock=bool(d.in_stock),
            retailer_id=d.retailer_id,
            retailer_name=d.retailer.name,
            product_url=d.product_url,
            promo_codes=[
                PublicPromoCode(
                    code=c.code,
                    description=c.description,
                    discount_percent=c.discount_percent,
                    discount_amount=c.discount_amount,
                )
                for c in d.retailer.active_promo_codes
            ],
            detected_at=d.detected_at,
        )
        for d in list_deals(db, is_active=True)
    ]
    checked_at = (
        db.query(func.max(ScrapeRun.finished_at))
        .filter(ScrapeRun.status == "success")
        .scalar()
    )
    return PublicDealsResponse(deals=deals, checked_at=checked_at)
