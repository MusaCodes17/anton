"""Pydantic response models for the longitudinal analytics endpoints (R5.5).

Mirror the dataclasses in app.services.insights field for field; the MCP tools
return `model_dump()` of these same models, so REST and MCP cannot drift."""
from typing import List, Optional

from pydantic import BaseModel


class ShoePerformanceResponse(BaseModel):
    owned_shoe_id: int
    runs: int
    km: float
    steady_runs: int
    median_m_per_beat: Optional[float] = None
    median_pace_s_per_km: Optional[int] = None
    median_avg_hr: Optional[int] = None
    enough_data: bool
    min_steady_runs: int
    heuristic: bool
    caveat: str


class ModelPerformanceResponse(BaseModel):
    brand: str
    model: str
    pair_ids: List[int]
    runs: int
    km: float
    steady_runs: int
    median_m_per_beat: Optional[float] = None
    median_pace_s_per_km: Optional[int] = None
    median_avg_hr: Optional[int] = None
    enough_data: bool
    min_steady_runs: int
    heuristic: bool
    caveat: str


class WearWeekResponse(BaseModel):
    week: str
    km: float
    cumulative_km: float


class WearCurveResponse(BaseModel):
    owned_shoe_id: int
    weeks: List[WearWeekResponse]
    current_mileage: float
    mileage_limit: Optional[float] = None
    pct_of_limit: Optional[float] = None
    status: str


class TypeWearResponse(BaseModel):
    shoe_type: str
    retired_count: int
    median_final_km: float
    default_limit_km: float
    suggested_limit_km: Optional[float] = None


class ShoeInsightsResponse(BaseModel):
    performance: ShoePerformanceResponse
    model: ModelPerformanceResponse
    wear: WearCurveResponse
    type_wear: Optional[TypeWearResponse] = None


class RotationInsightsResponse(BaseModel):
    models: List[ModelPerformanceResponse]
    wear_by_type: List[TypeWearResponse]
