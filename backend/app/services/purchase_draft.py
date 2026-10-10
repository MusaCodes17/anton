"""
A read-only bridge from the deals domain to the rotation domain (R5.3, "Bought it").

Given a deal the runner is looking at, build the *draft* of an owned-shoe record
(brand, model, price paid, date, retailer, URL) that the add-shoe form can be
prefilled with. Nothing is linked or written: the draft carries `deal_id` only as
a reference for the caller, and saving goes through the existing owned-shoe
create path. This is the B1 rule in practice — wanting a shoe (a deal) and owning
one (an owned shoe) stay independent, joined by recorded strings, never by FK.

Every field stays editable in the UI because the price actually paid often
differs from the deal's `current_price` (coupon, size, in-store).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Deal
from app.services.training_trends import toronto_today
from app.utils.shoe_types import is_valid_shoe_type


@dataclass
class PurchaseDraft:
    """A prefill for the add-owned-shoe form. Not persisted; not a link to the deal."""
    brand: str
    model: str
    shoe_type: Optional[str]     # watchlist type only if it is in the owned-shoe vocabulary
    purchase_price: float        # the deal's current_price; the runner may edit it
    purchase_date: date          # Toronto "today" unless pinned by the caller
    purchase_retailer: Optional[str]
    purchase_url: Optional[str]
    image_url: Optional[str]
    colorway: Optional[str]
    deal_id: int
    deal_active: bool            # False if the deal has since expired; still draftable


def purchase_draft_from_deal(
    db: Session, deal_id: int, *, today: Optional[date] = None
) -> PurchaseDraft:
    """Draft an owned-shoe record from a deal. Read-only: never adds or updates rows.

    Inactive deals still draft (`deal_active=False`) because the runner may have
    bought the shoe before the deal expired.

    Raises:
        LookupError: no deal with `deal_id`.
    """
    deal = db.get(Deal, deal_id)
    if deal is None:
        raise LookupError(f"Deal {deal_id} not found")

    shoe = deal.shoe
    # Watchlist shoe_type is free-ish text on Shoe; only pass it through when it is
    # a value the owned-shoe side understands, so the join key stays schema-grade.
    shoe_type = shoe.shoe_type if is_valid_shoe_type(shoe.shoe_type) else None

    return PurchaseDraft(
        brand=shoe.brand,
        model=shoe.model,
        shoe_type=shoe_type,
        purchase_price=deal.current_price,
        purchase_date=today or toronto_today(),
        purchase_retailer=deal.retailer.name,
        purchase_url=deal.product_url,
        image_url=deal.image_url,
        colorway=deal.colorway,
        deal_id=deal.id,
        deal_active=bool(deal.is_active),
    )
