"""
Watchlist read model — the data behind the redesigned Deals page (Phase 2).

Answers "what am I watching and what's actionable" for every tracked shoe in
one pass, not just the on-sale subset: current best active deal (if any),
best-ever price + when, and the last-seen price at each retailer.

R2.3: extracted out of `routers/watchlist.py` so the reduction is a service
(the router is now a thin adapter, CLAUDE.md §4.1) and the same computation can
back an MCP watchlist tool/resource (R3.4 parity) without re-deriving it.

Performance: the price-history reduction (best-ever per shoe, latest per
shoe+retailer) is done in SQL with window functions (SQLite >= 3.25) and
selects columns only — loading ~28k PriceRecord ORM objects used to dominate
the request. Python now only shapes ~N shoes x retailers rows (CLAUDE.md §12).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
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

    # Best-ever per shoe, reduced in SQL. Tie rule: lowest price, then lowest id
    # (the old Python loop used strict `<` in id order, i.e. first record wins).
    best_rn = (
        func.row_number()
        .over(
            partition_by=PriceRecord.shoe_id,
            order_by=(PriceRecord.price.asc(), PriceRecord.id.asc()),
        )
        .label("rn")
    )
    best_sq = (
        select(PriceRecord.shoe_id, PriceRecord.price, PriceRecord.scraped_at, best_rn)
        .where(PriceRecord.shoe_id.in_(shoe_ids))
        .subquery()
    )
    best_ever: dict[int, tuple] = {
        row.shoe_id: (row.price, row.scraped_at)
        for row in db.execute(
            select(best_sq.c.shoe_id, best_sq.c.price, best_sq.c.scraped_at).where(best_sq.c.rn == 1)
        )
    }

    # Latest record per (shoe, retailer): non-null scraped_at beats null, then
    # newest scraped_at, then highest id. first_id (min id of the pair) preserves
    # the old dict-insertion order, which the image fallback below depends on.
    latest_rn = (
        func.row_number()
        .over(
            partition_by=(PriceRecord.shoe_id, PriceRecord.retailer_id),
            order_by=(
                PriceRecord.scraped_at.is_not(None).desc(),
                PriceRecord.scraped_at.desc(),
                PriceRecord.id.desc(),
            ),
        )
        .label("rn")
    )
    first_id = (
        func.min(PriceRecord.id)
        .over(partition_by=(PriceRecord.shoe_id, PriceRecord.retailer_id))
        .label("first_id")
    )
    # Window over narrow columns only (ids), then join back for the payload —
    # carrying product_url/image_url Text through the window sort was the bulk
    # of the remaining cost.
    latest_sq = (
        select(PriceRecord.id, PriceRecord.shoe_id, PriceRecord.retailer_id, latest_rn, first_id)
        .where(PriceRecord.shoe_id.in_(shoe_ids))
        .subquery()
    )
    latest_stmt = (
        select(
            PriceRecord.shoe_id, PriceRecord.retailer_id, PriceRecord.price,
            PriceRecord.in_stock, PriceRecord.product_url, PriceRecord.scraped_at,
            PriceRecord.image_url,
        )
        .join(latest_sq, latest_sq.c.id == PriceRecord.id)
        .where(latest_sq.c.rn == 1)
        .order_by(latest_sq.c.first_id)
    )
    latest_by_shoe: dict[int, list] = {}
    for row in db.execute(latest_stmt):
        latest_by_shoe.setdefault(row.shoe_id, []).append(row)

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

        best_rec = best_ever.get(shoe.id)  # (price, scraped_at) or None
        latest_rows = latest_by_shoe.get(shoe.id, [])

        last_seen = [
            WatchlistLastSeen(
                retailer_id=rec.retailer_id,
                retailer_name=retailer_names.get(rec.retailer_id, "Unknown"),
                price=rec.price,
                in_stock=rec.in_stock,
                product_url=rec.product_url,
                scraped_at=rec.scraped_at,
            )
            for rec in latest_rows
        ]
        last_seen.sort(key=lambda ls: ls.price)

        # Image fallback: best deal's image → any recent price-record image.
        if image_url is None:
            for rec in latest_rows:
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
                best_ever_price=best_rec[0] if best_rec else None,
                best_ever_at=best_rec[1] if best_rec else None,
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
