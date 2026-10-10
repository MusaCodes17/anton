"""
Pydantic schemas for the personal rotation domain: owned shoes, their
mileage/review fields, runs logged against them, and shoe journal notes.
Re-exported from `app.models.schemas`.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.schemas._common import validate_optional_shoe_type, validate_owned_shoe_status


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
    _check_status = field_validator("status")(validate_owned_shoe_status)


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
    _check_status = field_validator("status")(validate_owned_shoe_status)


class MileageAdjust(BaseModel):
    """
    Body for POST /owned-shoes/{id}/adjust-mileage — a sanctioned manual
    override of the mileage ledger, routed through rotation.adjust_mileage so
    the drift from the run-sum identity is recorded (C1 fix).
    """
    new_mileage: float = Field(..., ge=0, description="The corrected current mileage, km")


class ShoeReviewUpdate(BaseModel):
    """Body for PATCH /owned-shoes/{id}/review (R3.3 — shoe review pipeline)."""
    review_text: str = Field(..., min_length=1, description="Review draft text to store on the shoe")


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
    review_draft: Optional[str] = Field(
        None, description="Runner-authored or LLM-drafted review stored on the shoe (R3.3)"
    )
    recommended_limit_km: Optional[float] = Field(
        None, description="Default retirement limit for this shoe_type (derived); mileage_limit is the runner's own call"
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
