"""
Coupon-stacking opportunity service (R4.4).

Reads the current DB state and surfaces the intersection of active promo
codes and active deals — the "stackable" retailers where a discount code
can be applied on top of an already-below-MSRP deal.

Read-only and derived-never-stored (CLAUDE.md §7): no writes here; actual
code discovery goes through ScrapeOrchestrator.detect_all_promo_codes →
DealStore.upsert_promo_code (the existing sanctioned write path).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import Deal, PromoCode, Retailer, Shoe


def _promo_entry(pc: PromoCode) -> dict:
    return {
        "code": pc.code,
        "description": pc.description,
        "discount_percent": pc.discount_percent,
        "source": pc.source,
        "last_seen_at": pc.last_seen_at.isoformat() if pc.last_seen_at else None,
    }


def _deal_entry(deal: Deal, shoe: Shoe) -> dict:
    return {
        "shoe": f"{shoe.brand} {shoe.model}",
        "price": deal.current_price,
        "savings_percent": deal.savings_percent,
        "product_url": deal.product_url,
    }


def get_stacking_opportunities(db: Session) -> dict:
    """
    Return active promo codes per retailer, annotated with active deals.

    "Stackable" = a retailer that has BOTH at least one active promo code
    AND at least one active deal (price < MSRP) right now.  Stacking the
    code on the deal compounds the saving.

    Returns:
        all_retailers      list of every active retailer with ≥1 active code
        stackable          subset that also has ≥1 active deal
        total_active_codes int — active code count across all retailers
        stackable_count    int — len(stackable)
    """
    # Retailers with at least one active promo code, ordered by name.
    retailers_with_codes = (
        db.query(Retailer)
        .filter(Retailer.is_active == True)  # noqa: E712
        .join(PromoCode, PromoCode.retailer_id == Retailer.id)
        .filter(PromoCode.is_active == True)  # noqa: E712
        .distinct()
        .order_by(Retailer.name)
        .all()
    )

    # Active codes per retailer.
    retailer_ids = [r.id for r in retailers_with_codes]
    codes_by_retailer: dict[int, list] = {rid: [] for rid in retailer_ids}
    for pc in (
        db.query(PromoCode)
        .filter(PromoCode.retailer_id.in_(retailer_ids), PromoCode.is_active == True)  # noqa: E712
        .all()
    ):
        codes_by_retailer[pc.retailer_id].append(_promo_entry(pc))

    # Active deals per retailer (for those that have codes).
    deals_by_retailer: dict[int, list] = {rid: [] for rid in retailer_ids}
    for deal in (
        db.query(Deal)
        .filter(Deal.retailer_id.in_(retailer_ids), Deal.is_active == True)  # noqa: E712
        .all()
    ):
        shoe = db.query(Shoe).filter(Shoe.id == deal.shoe_id).first()
        if shoe:
            deals_by_retailer[deal.retailer_id].append(_deal_entry(deal, shoe))

    all_retailers = []
    stackable = []
    total_active_codes = 0

    for r in retailers_with_codes:
        codes = codes_by_retailer[r.id]
        deals = deals_by_retailer[r.id]
        total_active_codes += len(codes)
        entry = {
            "retailer_id": r.id,
            "name": r.name,
            "promo_codes": codes,
            "deals": deals,
        }
        all_retailers.append(entry)
        if deals:
            stackable.append(entry)

    return {
        "all_retailers": all_retailers,
        "stackable": stackable,
        "total_active_codes": total_active_codes,
        "stackable_count": len(stackable),
    }
