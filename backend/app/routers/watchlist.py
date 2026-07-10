"""
Watchlist API — the data behind the redesigned Deals page (Phase 2).

Answers "what am I watching and what's actionable" for every tracked shoe in
one round trip, not just the on-sale subset: current best active deal (if
any), best-ever price + when, and the last-seen price at each retailer.

Deliberately one endpoint so the page (and the future mobile client) loads
the whole watchlist in a single request. Thin adapter over
`services.watchlist.build_watchlist` (R2.3) — the reduction lives in the
service; this file only shapes the HTTP response.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import watchlist as watchlist_svc

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class LastSeenPrice(BaseModel):
    """Most recent price for a shoe at one retailer."""
    model_config = ConfigDict(from_attributes=True)  # read the service dataclasses
    retailer_id: int
    retailer_name: str
    price: float
    in_stock: bool
    product_url: str
    scraped_at: Optional[datetime] = None


class WatchlistDeal(BaseModel):
    """Compact view of a shoe's best active deal (lowest current price)."""
    model_config = ConfigDict(from_attributes=True)
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
    model_config = ConfigDict(from_attributes=True)
    shoe_id: int
    brand: str
    model: str
    shoe_type: Optional[str] = None
    target_price: Optional[float] = None
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
    last-seen price per retailer, already ordered on-sale-first (see
    `services.watchlist.build_watchlist`). Pydantic reads the service dataclasses
    field-for-field via `from_attributes`.
    """
    return watchlist_svc.build_watchlist(db)
