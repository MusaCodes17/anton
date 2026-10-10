"""
Pydantic schemas for the training domain: planned races and race readiness.
Re-exported from `app.models.schemas`.
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


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


class PlannedRaceLinkActivity(BaseModel):
    """Link a past race to the run that was the race (R8.3)."""
    activity_id: int


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
    # True when synthesized from an Activity tag, not a PlannedRace row — frontend
    # uses this to suppress edit/done/delete actions on activity-sourced entries.
    from_activity: bool = False

    class Config:
        from_attributes = True


# --- Race readiness (R8.4.4) — mirrors services.race_advisor.RaceReadiness ---

class ReadinessRaceResponse(BaseModel):
    id: int
    name: str
    race_date: str
    distance_km: Optional[float] = None
    status: str
    days_to_race: int
    weeks_to_race: int
    target_time_s: Optional[int] = None
    target_pace: Optional[str] = None
    target_pace_s_per_km: Optional[int] = None


class ReadinessWeekResponse(BaseModel):
    period: str                       # ISO week key, as the Volume chart
    total_km: float
    run_count: int


class ReadinessRunResponse(BaseModel):
    run_date: str
    distance_km: float
    name: Optional[str] = None
    activity_id: Optional[int] = None


class ReadinessEffortResponse(BaseModel):
    label: str
    distance_km: float
    time_s: int
    pace: str
    pace_s_per_km: int
    vs_target_s_per_km: Optional[int] = None   # negative = faster than target pace
    run_date: Optional[str] = None
    name: Optional[str] = None
    activity_id: Optional[int] = None
    segment: bool = False


class ReadinessChecklistItem(BaseModel):
    key: str                          # weeks_to_go | peak_week | longest_run | long_runs | key_effort
    label: str
    status: str                       # met | not_met | info | n/a
    rule: Optional[str] = None
    value: Optional[float] = None
    target: Optional[float] = None
    unit: str


class RaceReadinessResponse(BaseModel):
    """"Am I ready for race X?" — a checklist with numbers, not a score (R8.4.4).
    `has_race` False → no race ahead; the readiness card hides."""
    has_race: bool
    as_of: str
    race: Optional[ReadinessRaceResponse] = None
    race_class: Optional[str] = None
    block_weeks: Optional[int] = None
    block_start: Optional[str] = None
    block_end: Optional[str] = None
    block_started: bool = False
    block_km: float = 0.0
    block_runs: int = 0
    peak_week: Optional[ReadinessWeekResponse] = None
    current_week: Optional[ReadinessWeekResponse] = None
    longest_run: Optional[ReadinessRunResponse] = None
    long_run_km: Optional[float] = None
    long_runs_needed: int
    long_runs: List[ReadinessRunResponse] = []
    effort_window_start: Optional[str] = None
    key_effort: Optional[str] = None
    recent_efforts: List[ReadinessEffortResponse] = []
    checklist: List[ReadinessChecklistItem] = []
    heuristic: bool = True
