"""Watchlist response schemas (shared by the REST router and the MCP server)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


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
