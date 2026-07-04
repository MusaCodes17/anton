"""
Watchlist API — the data behind the redesigned Deals page (Phase 2).

Answers "what am I watching and what's actionable" for every tracked shoe in
one round trip, not just the on-sale subset: current best active deal (if
any), best-ever price + when, and the last-seen price at each retailer.

Deliberately one endpoint so the page (and the future mobile client) loads
the whole watchlist in a single request.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Deal, PriceRecord, Retailer, Shoe

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class LastSeenPrice(BaseModel):
    """Most recent price for a shoe at one retailer."""
    retailer_id: int
    retailer_name: str
    price: float
    in_stock: bool
    product_url: str
    scraped_at: Optional[datetime] = None


class WatchlistDeal(BaseModel):
    """Compact view of a shoe's best active deal (lowest current price)."""
    deal_id: int
    retailer_id: int
    retailer_name: str
    current_price: float
    savings_percent: float
    savings_amount: float
    product_url: str
    in_stock: bool


class WatchlistItem(BaseModel):
    """One tracked shoe with everything the watchlist row needs."""
    shoe_id: int
    brand: str
    model: str
    shoe_type: Optional[str] = None
    target_price: float
    msrp: Optional[float] = None
    image_url: Optional[str] = None
    on_sale: bool
    best_deal: Optional[WatchlistDeal] = None
    best_ever_price: Optional[float] = None
    best_ever_at: Optional[datetime] = None
    last_seen: List[LastSeenPrice] = []


@router.get("", response_model=List[WatchlistItem])
@router.get("/", response_model=List[WatchlistItem])
def get_watchlist(db: Session = Depends(get_db)):
    """
    Every actively-tracked shoe with its best deal, best-ever price, and
    last-seen price per retailer. On-sale shoes sort first (by savings %),
    then the rest alphabetically — so the caller can split the list into
    "on sale now" and "watching" without re-sorting.
    """
    shoes = db.query(Shoe).filter(Shoe.is_active == True).all()  # noqa: E712
    if not shoes:
        return []

    shoe_ids = [s.id for s in shoes]
    retailer_names = {r.id: r.name for r in db.query(Retailer).all()}

    # Active deals for these shoes, grouped by shoe (best = lowest price).
    deals_by_shoe: dict[int, list[Deal]] = {}
    for deal in (
        db.query(Deal)
        .filter(Deal.is_active == True, Deal.shoe_id.in_(shoe_ids))  # noqa: E712
        .all()
    ):
        deals_by_shoe.setdefault(deal.shoe_id, []).append(deal)

    # One pass over every relevant price record → best-ever + latest-per-retailer.
    # Personal scale (dozens of shoes, a few thousand records) makes reducing in
    # Python cheaper and clearer than several correlated aggregate subqueries.
    best_ever: dict[int, PriceRecord] = {}
    latest_per_retailer: dict[tuple[int, int], PriceRecord] = {}
    for rec in (
        db.query(PriceRecord)
        .filter(PriceRecord.shoe_id.in_(shoe_ids))
        .all()
    ):
        prev_best = best_ever.get(rec.shoe_id)
        if prev_best is None or rec.price < prev_best.price:
            best_ever[rec.shoe_id] = rec

        key = (rec.shoe_id, rec.retailer_id)
        prev_latest = latest_per_retailer.get(key)
        if prev_latest is None or _scraped_key(rec) > _scraped_key(prev_latest):
            latest_per_retailer[key] = rec

    items: List[WatchlistItem] = []
    for shoe in shoes:
        active_deals = deals_by_shoe.get(shoe.id, [])
        best_deal_row = min(active_deals, key=lambda d: d.current_price, default=None)

        best_deal = None
        image_url = None
        if best_deal_row is not None:
            best_deal = WatchlistDeal(
                deal_id=best_deal_row.id,
                retailer_id=best_deal_row.retailer_id,
                retailer_name=retailer_names.get(best_deal_row.retailer_id, "Unknown"),
                current_price=best_deal_row.current_price,
                savings_percent=best_deal_row.savings_percent,
                savings_amount=best_deal_row.savings_amount,
                product_url=best_deal_row.product_url,
                in_stock=best_deal_row.in_stock,
            )
            image_url = best_deal_row.image_url

        best_rec = best_ever.get(shoe.id)

        last_seen = [
            LastSeenPrice(
                retailer_id=rec.retailer_id,
                retailer_name=retailer_names.get(rec.retailer_id, "Unknown"),
                price=rec.price,
                in_stock=rec.in_stock,
                product_url=rec.product_url,
                scraped_at=rec.scraped_at,
            )
            for (sid, _rid), rec in latest_per_retailer.items()
            if sid == shoe.id
        ]
        last_seen.sort(key=lambda ls: ls.price)

        # Image fallback: best deal's image → any recent price-record image.
        if image_url is None:
            for rec in (r for (sid, _), r in latest_per_retailer.items() if sid == shoe.id):
                if rec.image_url:
                    image_url = rec.image_url
                    break

        items.append(
            WatchlistItem(
                shoe_id=shoe.id,
                brand=shoe.brand,
                model=shoe.model,
                shoe_type=shoe.shoe_type,
                target_price=shoe.target_price,
                msrp=shoe.msrp,
                image_url=image_url,
                on_sale=bool(active_deals),
                best_deal=best_deal,
                best_ever_price=best_rec.price if best_rec else None,
                best_ever_at=best_rec.scraped_at if best_rec else None,
                last_seen=last_seen,
            )
        )

    # On-sale first (deepest discount first), then the watched rest A→Z.
    items.sort(
        key=lambda it: (
            0 if it.on_sale else 1,
            -(it.best_deal.savings_percent if it.best_deal else 0),
            it.brand.lower(),
            it.model.lower(),
        )
    )
    return items


def _scraped_key(rec: PriceRecord):
    """Sort key for 'latest' that tolerates a null scraped_at (falls back to id).

    The leading has-timestamp flag keeps a naive fallback from ever being
    compared against a (possibly tz-aware) real scraped_at.
    """
    return (rec.scraped_at is not None, rec.scraped_at or datetime.min, rec.id)
