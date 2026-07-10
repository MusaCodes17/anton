"""
Watchlist read model — the data behind the redesigned Deals page (Phase 2).

Answers "what am I watching and what's actionable" for every tracked shoe in
one pass, not just the on-sale subset: current best active deal (if any),
best-ever price + when, and the last-seen price at each retailer.

R2.3: extracted out of `routers/watchlist.py` so the reduction is a service
(the router is now a thin adapter, CLAUDE.md §4.1) and the same computation can
back an MCP watchlist tool/resource (R3.4 parity) without re-deriving it.

Personal scale (dozens of shoes, a few thousand price records) makes reducing
in Python cheaper and clearer than several correlated aggregate subqueries —
this is a labelled O(N) whole-table pass, not an oversight (CLAUDE.md §12).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Deal, PriceRecord, Retailer, Shoe


@dataclass
class WatchlistLastSeen:
    """Most recent price for a shoe at one retailer."""
    retailer_id: int
    retailer_name: str
    price: float
    in_stock: bool
    product_url: str
    scraped_at: Optional[datetime] = None


@dataclass
class WatchlistBestDeal:
    """Compact view of a shoe's best active deal (lowest current price)."""
    deal_id: int
    retailer_id: int
    retailer_name: str
    current_price: float
    savings_percent: float
    savings_amount: float
    product_url: str
    in_stock: bool


@dataclass
class WatchlistEntry:
    """One tracked shoe with everything the watchlist row needs."""
    shoe_id: int
    brand: str
    model: str
    on_sale: bool
    shoe_type: Optional[str] = None
    target_price: Optional[float] = None
    msrp: Optional[float] = None
    image_url: Optional[str] = None
    best_deal: Optional[WatchlistBestDeal] = None
    best_ever_price: Optional[float] = None
    best_ever_at: Optional[datetime] = None
    last_seen: list[WatchlistLastSeen] = field(default_factory=list)


def _scraped_key(rec: PriceRecord):
    """Sort key for 'latest' that tolerates a null scraped_at (falls back to id).

    The leading has-timestamp flag keeps a naive fallback from ever being
    compared against a (possibly tz-aware) real scraped_at.
    """
    return (rec.scraped_at is not None, rec.scraped_at or datetime.min, rec.id)


def build_watchlist(db: Session) -> list[WatchlistEntry]:
    """
    Every actively-tracked shoe with its best deal, best-ever price, and
    last-seen price per retailer. On-sale shoes sort first (by savings %), then
    the rest alphabetically — so the caller can split the list into "on sale
    now" and "watching" without re-sorting.
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

    entries: list[WatchlistEntry] = []
    for shoe in shoes:
        active_deals = deals_by_shoe.get(shoe.id, [])
        best_deal_row = min(active_deals, key=lambda d: d.current_price, default=None)

        best_deal = None
        image_url = None
        if best_deal_row is not None:
            best_deal = WatchlistBestDeal(
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
            WatchlistLastSeen(
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

        entries.append(
            WatchlistEntry(
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
    entries.sort(
        key=lambda e: (
            0 if e.on_sale else 1,
            -(e.best_deal.savings_percent if e.best_deal else 0),
            e.brand.lower(),
            e.model.lower(),
        )
    )
    return entries
