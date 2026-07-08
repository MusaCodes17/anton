"""
Pydantic schemas for API request/response validation
"""
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import List, Optional
from datetime import date, datetime

from app.utils.shoe_types import SHOE_TYPES, is_valid_shoe_type


def validate_optional_shoe_type(v: Optional[str]) -> Optional[str]:
    """Shared `shoe_type` validator for the write schemas (R2.4): `None`/`""`
    clears the type; any other value must be a member of the backend-owned
    vocabulary (`app.utils.shoe_types.SHOE_TYPES`). Rejects typos that used to
    fail silently at the cross-domain join. Read schemas deliberately do NOT
    validate — legacy data must never break a GET."""
    if v is None or v == "":
        return None
    if not is_valid_shoe_type(v):
        raise ValueError(
            f"Invalid shoe_type '{v}'. Use one of: {', '.join(SHOE_TYPES)} (or omit)."
        )
    return v


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

class RetailerBase(BaseModel):
    """Base schema for retailer data"""
    name: str = Field(..., min_length=1, max_length=200, description="Retailer name")
    base_url: str = Field(..., description="Retailer base URL")
    is_active: bool = Field(True, description="Whether retailer is enabled")
    scraping_enabled: bool = Field(True, description="Whether to scrape this retailer")
    scraper_config: Optional[dict] = Field(
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
    scraper_config: Optional[dict] = None
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
    expires_at: Optional[datetime] = None
    
    # Include related shoe and retailer info
    shoe: Optional[ShoeResponse] = None
    retailer: Optional[RetailerResponse] = None

    class Config:
        from_attributes = True


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


# ============== OWNED SHOE SCHEMAS ==============

class OwnedShoeBase(BaseModel):
    """Base schema for a shoe in the user's personal rotation"""
    brand: str = Field(..., min_length=1, max_length=100, description="Shoe brand")
    model: str = Field(..., min_length=1, max_length=200, description="Shoe model")
    nickname: Optional[str] = Field(None, max_length=100, description="Personal nickname, e.g. 'Race day Adios'")
    shoe_type: Optional[str] = Field(None, max_length=50, description="e.g. 'Tempo shoe'")
    purchase_date: Optional[date] = Field(None, description="When the shoe was purchased")
    starting_mileage: float = Field(0, ge=0, description="km already on the shoe when added")
    status: str = Field("active", description="active | retired | for_sale")
    purchase_price: Optional[float] = Field(None, gt=0, description="What was paid for the shoe")
    mileage_limit: Optional[float] = Field(None, gt=0, description="km at which this shoe should be retired (user-set)")
    image_url: Optional[str] = Field(None, description="Manually-set product image URL")


class OwnedShoeCreate(OwnedShoeBase):
    """Schema for adding a shoe to the rotation"""
    _check_shoe_type = field_validator("shoe_type")(validate_optional_shoe_type)


class OwnedShoeUpdate(BaseModel):
    """
    Schema for updating an owned shoe (all fields optional).

    Deliberately omits `current_mileage` and `starting_mileage` (C1 fix,
    2026-07-07): the mileage ledger is `current_mileage = starting_mileage +
    Σ attributed distances` (INV-1) and may not be set through this blind
    setattr path. `current_mileage` is corrected only via the sanctioned
    POST /owned-shoes/{id}/adjust-mileage (rotation.adjust_mileage), which
    records the override; `starting_mileage` is the ledger anchor, fixed at
    creation. Any client that still sends either field has it silently ignored.
    """
    brand: Optional[str] = Field(None, min_length=1, max_length=100)
    model: Optional[str] = Field(None, min_length=1, max_length=200)
    nickname: Optional[str] = Field(None, max_length=100)
    shoe_type: Optional[str] = Field(None, max_length=50)
    purchase_date: Optional[date] = None
    status: Optional[str] = None
    purchase_price: Optional[float] = Field(None, gt=0)
    mileage_limit: Optional[float] = Field(None, gt=0)
    image_url: Optional[str] = None

    _check_shoe_type = field_validator("shoe_type")(validate_optional_shoe_type)


class MileageAdjust(BaseModel):
    """
    Body for POST /owned-shoes/{id}/adjust-mileage — a sanctioned manual
    override of the mileage ledger, routed through rotation.adjust_mileage so
    the drift from the run-sum identity is recorded (C1 fix).
    """
    new_mileage: float = Field(..., ge=0, description="The corrected current mileage, km")


class OwnedShoeResponse(OwnedShoeBase):
    """Schema for owned shoe response"""
    id: int
    matched_image_url: Optional[str] = Field(
        None, description="Best-effort image match from price_records, used when image_url isn't set"
    )
    current_mileage: float
    lifetime_avg_pace: Optional[str] = Field(
        None, description="Lifetime average pace across all logged runs with a recorded pace, 'M:SS/km'"
    )
    lifetime_avg_hr: Optional[int] = Field(
        None, description="Lifetime average heart rate across all logged runs with a recorded HR (bpm)"
    )
    total_runs: int = Field(0, description="Count of runs logged against this shoe")
    cost_per_km: Optional[float] = Field(
        None, description="purchase_price / current_mileage, rounded to 2 decimals — only when both are set"
    )
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============== SHOE RUN SCHEMAS ==============

class ShoeRunBase(BaseModel):
    """Base schema for a run logged against an owned shoe"""
    distance_km: float = Field(..., gt=0, description="Distance covered in this run")
    run_date: date = Field(..., description="Date the run took place")
    avg_pace: Optional[str] = Field(None, max_length=20, description="e.g. '4:35/km'")
    avg_hr: Optional[int] = Field(None, gt=0, description="Average heart rate (bpm)")
    notes: Optional[str] = Field(None, description="Notes about this run")


class ShoeRunCreate(ShoeRunBase):
    """Schema for manually logging a run (POST /owned-shoes/{id}/log-run)"""
    pass


class ShoeRunResponse(ShoeRunBase):
    """Schema for run response"""
    # Manual creation requires distance > 0 (ShoeRunBase), but some historical
    # COROS-synced runs were deliberately logged at 0km to avoid double-counting
    # mileage that had already been added manually (the real distance is kept in
    # the note). Responses must therefore allow 0 so those runs still serialize
    # and appear in run history instead of 500ing the endpoint.
    distance_km: float = Field(..., ge=0, description="Distance covered in this run")
    id: int
    owned_shoe_id: int
    source: str
    coros_activity_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LogRunResponse(BaseModel):
    """
    Response for POST /owned-shoes/{id}/log-run. Carries the updated shoe
    plus a checkpoint flag so the frontend can prompt for a notes-journal
    entry when a logged run crosses a 100km boundary (100, 200, 300...).
    """
    run_logged: bool = True
    updated_mileage: float
    checkpoint_reached: bool = False
    checkpoint_km: Optional[int] = None
    shoe: OwnedShoeResponse


# ============== SHOE NOTE SCHEMAS ==============

# ============== COROS SYNC SCHEMAS ==============

class CorosRun(BaseModel):
    """A single unsynced run fetched from the COROS API."""
    coros_activity_id: str
    date: str  # YYYY-MM-DD
    distance_km: float
    avg_pace: Optional[str] = None  # "M:SS/km"
    avg_hr: Optional[int] = None
    sport_type: int
    name: str


class CorosFetchResponse(BaseModel):
    """Response for POST /owned-shoes/sync-coros/fetch."""
    runs: List[CorosRun]
    already_synced: int
    coros_configured: bool


class CorosAssignment(BaseModel):
    """One user-confirmed COROS run → owned shoe assignment."""
    coros_activity_id: str
    owned_shoe_id: int
    date: str  # YYYY-MM-DD
    distance_km: float
    avg_pace: Optional[str] = None
    avg_hr: Optional[int] = None
    notes: Optional[str] = None


class CorosConfirmRequest(BaseModel):
    """Request body for POST /owned-shoes/sync-coros/confirm."""
    assignments: List[CorosAssignment]


class CorosConfirmResponse(BaseModel):
    """Summary of logged runs after a COROS sync confirmation."""
    logged: int
    updated_shoes: List[OwnedShoeResponse]


class CorosSyncStatus(BaseModel):
    """Response for GET /owned-shoes/sync-coros/status."""
    coros_configured: bool
    last_sync_at: Optional[datetime] = None
    pending_runs: int = 0


class ShoeNoteCreate(BaseModel):
    """Schema for adding a journal entry to an owned shoe"""
    body: str = Field(..., min_length=1, description="The note content")
    triggered_by: str = Field("manual", description="manual | checkpoint")


class ShoeNoteResponse(BaseModel):
    """Schema for a shoe journal entry"""
    id: int
    owned_shoe_id: int
    body: str
    mileage_at_note: float
    triggered_by: str
    created_at: datetime

    class Config:
        from_attributes = True


# ============== PLANNED RACE SCHEMAS ==============

class PlannedRaceBase(BaseModel):
    """Shared fields for creating/updating a planned race."""
    name: str = Field(..., min_length=1, max_length=200)
    race_date: date
    distance_km: Optional[float] = Field(None, gt=0)
    target_time_s: Optional[int] = Field(None, gt=0, description="Goal finish time in seconds")
    location: Optional[str] = Field(None, max_length=200)
    planned_shoe_id: Optional[int] = None
    notes: Optional[str] = None


class PlannedRaceCreate(PlannedRaceBase):
    pass


class PlannedRaceUpdate(BaseModel):
    """Partial update — every field optional, including status/result on completion."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    race_date: Optional[date] = None
    distance_km: Optional[float] = Field(None, gt=0)
    target_time_s: Optional[int] = Field(None, gt=0)
    location: Optional[str] = Field(None, max_length=200)
    planned_shoe_id: Optional[int] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(planned|completed|skipped)$")
    result_time_s: Optional[int] = Field(None, gt=0)


class PlannedShoeBrief(BaseModel):
    """The planned shoe, inlined so the card needs no second request."""
    id: int
    brand: str
    model: str
    nickname: Optional[str] = None

    class Config:
        from_attributes = True


class PlannedRaceResponse(PlannedRaceBase):
    """A planned race plus server-computed countdown/pace (API-first, §2.1)."""
    id: int
    status: str
    result_time_s: Optional[int] = None
    activity_id: Optional[int] = None      # R2.7 T7 — linked run for a completed race
    created_at: datetime
    planned_shoe: Optional[PlannedShoeBrief] = None
    # Computed server-side:
    days_remaining: int
    weeks_remaining: int
    target_pace: Optional[str] = None      # "M:SS/km" from target_time_s / distance_km

    class Config:
        from_attributes = True
