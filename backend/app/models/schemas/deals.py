"""
Pydantic schemas for the deal-watching domain: watchlist shoes, retailers,
promo codes, price records, deals, dashboard stats and scrape requests.
Re-exported from `app.models.schemas`.
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.schemas._common import validate_optional_shoe_type
from app.scrapers.platform_detection import ALGOLIA_REQUIRED_KEYS


# ============== SHOE SCHEMAS ==============

class ShoeBase(BaseModel):
    """Base schema for shoe data"""
    brand: str = Field(..., min_length=1, max_length=100, description="Shoe brand")
    model: str = Field(..., min_length=1, max_length=200, description="Shoe model")
    shoe_type: Optional[str] = Field(None, max_length=50, description="Shoe category, e.g. 'long_distance_racer'")
    msrp: Optional[float] = Field(None, gt=0, description="Manufacturer's list price — drives deal qualification and savings %")
    target_price: Optional[float] = Field(None, gt=0, description="Optional personal 'ping me at' threshold — not used in savings math")
    notes: Optional[str] = Field(None, description="Additional notes")
    is_active: bool = Field(True, description="Whether to actively monitor this shoe")


class ShoeCreate(ShoeBase):
    """Schema for creating a new shoe"""
    _check_shoe_type = field_validator("shoe_type")(validate_optional_shoe_type)


class ShoeUpdate(BaseModel):
    """Schema for updating a shoe (all fields optional)"""
    brand: Optional[str] = Field(None, min_length=1, max_length=100)
    model: Optional[str] = Field(None, min_length=1, max_length=200)
    shoe_type: Optional[str] = Field(None, max_length=50)
    target_price: Optional[float] = Field(None, gt=0)
    msrp: Optional[float] = Field(None, gt=0)
    notes: Optional[str] = None
    is_active: Optional[bool] = None

    _check_shoe_type = field_validator("shoe_type")(validate_optional_shoe_type)


class ShoeResponse(ShoeBase):
    """Schema for shoe response"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============== RETAILER SCHEMAS ==============

class ScraperConfig(BaseModel):
    """Input schema for `Retailer.scraper_config`: validates the *types* of the
    known keys and the Algolia all-or-nothing rule at the API boundary (a
    malformed config 422s here instead of failing at scrape time). Unknown keys
    are allowed (bespoke scrapers read their own). The column stays plain JSON:
    use `as_stored()` to get the dict that is persisted."""
    model_config = ConfigDict(extra="allow")

    algolia_app_id: Optional[str] = None
    algolia_api_key: Optional[str] = None
    algolia_index: Optional[str] = None
    algolia_product_path: Optional[str] = None
    homepage_url: Optional[str] = None
    search_selector: Optional[str] = None
    product_path: Optional[str] = None
    use_browser: Optional[bool] = None
    unscrapable: Optional[bool] = None
    unscrapable_reason: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _algolia_keys_all_or_nothing(self):
        if any(getattr(self, k) for k in ALGOLIA_REQUIRED_KEYS):
            missing = [k for k in ALGOLIA_REQUIRED_KEYS if not getattr(self, k)]
            if missing:
                raise ValueError(
                    "Algolia scraper_config needs all of "
                    f"{', '.join(ALGOLIA_REQUIRED_KEYS)}; missing: {', '.join(missing)}"
                )
        return self

    def as_stored(self) -> dict:
        """The plain dict to persist: unset keys omitted, extras included."""
        return self.model_dump(exclude_none=True)


class RetailerBase(BaseModel):
    """Base schema for retailer data"""
    name: str = Field(..., min_length=1, max_length=200, description="Retailer name")
    base_url: str = Field(..., description="Retailer base URL")
    is_active: bool = Field(True, description="Whether retailer is enabled")
    scraping_enabled: bool = Field(True, description="Whether to scrape this retailer")
    scraper_config: Optional[ScraperConfig] = Field(
        None,
        description=(
            "Scraper configuration. For platform='algolia' must include "
            "algolia_app_id, algolia_api_key, algolia_index."
        ),
    )


class RetailerCreate(RetailerBase):
    """Schema for creating a new retailer"""
    platform: Optional[str] = Field(
        None,
        description=(
            "'shopify', 'algolia', or 'custom'. If omitted, the platform is "
            "auto-detected: algolia credentials in scraper_config imply "
            "'algolia'; otherwise base_url is probed for a Shopify storefront; "
            "otherwise 'custom'. Shopify/algolia retailers get scraping_enabled "
            "forced True with a scraper wired up automatically; custom retailers "
            "get scraping_enabled forced False."
        ),
    )


class RetailerUpdate(BaseModel):
    """Schema for updating a retailer (all fields optional)"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    base_url: Optional[str] = None
    is_active: Optional[bool] = None
    scraping_enabled: Optional[bool] = None
    scraper_config: Optional[ScraperConfig] = None
    platform: Optional[str] = None


# ============== PROMO CODE SCHEMAS ==============

class PromoCodeBase(BaseModel):
    """Base schema for a discount/coupon code"""
    code: str = Field(..., min_length=2, max_length=50, description="The code customers enter, e.g. 20FOR200")
    description: Optional[str] = Field(None, description="Human-readable offer, e.g. 'Extra 20% off'")
    discount_percent: Optional[float] = Field(None, ge=0, le=100, description="Percentage discount")
    discount_amount: Optional[float] = Field(None, ge=0, description="Flat dollar discount")


class PromoCodeCreate(PromoCodeBase):
    """Schema for manually adding a promo code"""
    pass


class PromoCodeResponse(PromoCodeBase):
    """Schema for promo code response"""
    id: int
    retailer_id: int
    source: str
    source_url: Optional[str] = None
    is_active: bool
    detected_at: datetime
    last_seen_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RetailerResponse(RetailerBase):
    """Schema for retailer response"""
    id: int
    platform: str
    last_scraped_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    active_promo_codes: list[PromoCodeResponse] = []
    # Responses return the stored dict verbatim (legacy rows may hold keys or
    # shapes the input schema would reject); only inputs are validated.
    scraper_config: Optional[dict] = None

    class Config:
        from_attributes = True


class DealRetailerBrief(BaseModel):
    """Compact retailer embed for deal views: they need only the name and the
    active promo codes. The full RetailerResponse stays for /retailers."""
    id: int
    name: str
    active_promo_codes: list[PromoCodeResponse] = []

    class Config:
        from_attributes = True


# ============== PRICE RECORD SCHEMAS ==============

class PriceRecordBase(BaseModel):
    """Base schema for price record"""
    shoe_id: int
    retailer_id: int
    product_url: str
    price: float = Field(..., gt=0)
    original_price: Optional[float] = Field(None, gt=0)
    in_stock: bool = True
    # Scraper's "at least one size in stock" flag (written by the orchestrator);
    # distinct from a deal's `sizes_available` list — not a legacy duplicate.
    size_available: bool = True
    sizes_available: Optional[List[str]] = Field(None, description="Sizes in stock at scrape time")
    image_url: Optional[str] = Field(None, description="Product image URL")
    colorway: Optional[str] = Field(None, description="Colorway name")


class PriceRecordCreate(PriceRecordBase):
    """Schema for creating a price record"""
    pass


class PriceRecordResponse(PriceRecordBase):
    """Schema for price record response"""
    id: int
    scraped_at: datetime

    class Config:
        from_attributes = True


# ============== DEAL SCHEMAS ==============

class DealBase(BaseModel):
    """Base schema for deal"""
    shoe_id: int
    retailer_id: int
    current_price: float = Field(..., gt=0)
    target_price: Optional[float] = Field(None, gt=0)
    savings_amount: float = Field(..., ge=0)
    savings_percent: float = Field(..., ge=0, le=100)
    product_url: str
    in_stock: bool = True
    sizes_available: Optional[List[str]] = Field(None, description="Sizes in stock at scrape time")
    image_url: Optional[str] = Field(None, description="Product image URL")
    colorway: Optional[str] = Field(None, description="Colorway name")
    is_active: bool = True


class DealCreate(DealBase):
    """Schema for creating a deal"""
    pass


class DealResponse(DealBase):
    """Schema for deal response with related data"""
    id: int
    detected_at: datetime
    # R6.3 — derived per request from the size preference; None = no preference set.
    size_fit: Optional[str] = Field(None, description='"in" | "out" | "unknown" vs the preferred size')
    
    # Include related shoe and retailer info
    shoe: Optional[ShoeResponse] = None
    retailer: Optional[DealRetailerBrief] = None

    class Config:
        from_attributes = True


class PurchaseDraftResponse(BaseModel):
    """R5.3 — prefill for the add-owned-shoe form, built from a deal. Read-only:
    nothing here is stored or linked; the runner reviews and saves via POST /owned-shoes/."""
    brand: str
    model: str
    shoe_type: Optional[str] = Field(None, description="Watchlist type if it is in the owned-shoe vocabulary, else null")
    purchase_price: float = Field(..., description="The deal's current price; edit to the price actually paid")
    purchase_date: date = Field(..., description="Toronto local date of drafting, unless pinned")
    purchase_retailer: Optional[str] = None
    purchase_url: Optional[str] = None
    image_url: Optional[str] = None
    colorway: Optional[str] = None
    deal_id: int
    deal_active: bool = Field(..., description="False when the deal has expired; the draft is still valid")


# ============== DASHBOARD SCHEMAS ==============

class DashboardStats(BaseModel):
    """Schema for dashboard statistics"""
    total_shoes: int
    active_shoes: int
    total_retailers: int
    active_retailers: int
    active_deals: int
    total_price_records: int
    last_scrape: Optional[datetime] = None
    average_savings: Optional[float] = None


# ============== SCRAPING SCHEMAS ==============

class ScrapeResult(BaseModel):
    """Schema for scrape operation result"""
    success: bool
    retailer: str
    shoes_found: int
    deals_found: int
    errors: list[str] = []
    scraped_at: datetime


class ScrapeRequest(BaseModel):
    """Schema for manual scrape request"""
    retailer_ids: Optional[list[int]] = Field(None, description="Specific retailers to scrape (if None, scrape all)")
    shoe_ids: Optional[list[int]] = Field(None, description="Specific shoes to check (if None, check all)")


class ShoeTestRequest(BaseModel):
    """Schema for a scrapability test request (brand + model, no size)"""
    brand: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=200)
