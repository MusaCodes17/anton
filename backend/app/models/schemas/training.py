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


class ReadinessEvidenceRun(BaseModel):
    """A run behind a checklist number (R11.1)."""
    activity_id: Optional[int] = None
    run_date: str
    distance_km: float                # a segment's stretch distance when segment is true
    name: Optional[str] = None
    segment: bool = False


class ReadinessChecklistItem(BaseModel):
    key: str                          # weeks_to_go | peak_week | longest_run | long_runs | key_effort | race_shoe | (R11.3 info keys)
    label: str
    status: str                       # met | not_met | info | n/a | no_data
    rule: Optional[str] = None
    value: Optional[float] = None
    target: Optional[float] = None
    unit: str
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    evidence: List[ReadinessEvidenceRun] = []
    age_days: Optional[int] = None


class RaceShoeResponse(BaseModel):
    """The race's planned shoe (R11.5). projected_race_day_km is today's ledger plus
    the shoe's recent weekly rate over the race-day gap (a heuristic)."""
    shoe_id: int
    label: str
    status: str
    current_mileage: float
    mileage_limit: Optional[float] = None
    weekly_km: float
    projected_race_day_km: float
    block_runs: int = 0
    block_km: float = 0.0
    longest_km: Optional[float] = None
    last_run_date: Optional[str] = None


class BlockRaceResponse(BaseModel):
    id: int                           # negative for a Race-tagged run with no plan row
    name: str
    race_date: str                    # ISO date
    distance_km: Optional[float] = None
    status: str                       # completed | dnf | planned
    result_time_s: Optional[int] = None
    result_pace: Optional[str] = None     # "M:SS/km"
    target_time_s: Optional[int] = None
    target_pace: Optional[str] = None     # "M:SS/km"
    activity_id: Optional[int] = None
    from_activity: bool = False


class GapResponse(BaseModel):
    start: str                        # ISO date, first day off
    end: str                          # ISO date, last day off
    days: int


class ConsistencyResponse(BaseModel):
    """Block consistency (R11.3) — descriptive, no pass/fail."""
    weeks_elapsed: int
    weeks_with_runs: int
    median_runs_per_week: float
    gaps: List[GapResponse] = []


class TaperWeekResponse(BaseModel):
    offset: int                       # -2, -1, 0 (race week)
    week_start: str                   # ISO Monday
    km: float
    pct_of_peak: Optional[int] = None
    complete: bool


class TaperResponse(BaseModel):
    """The final three weeks against the block's peak (R11.3) — no target percentage."""
    peak_week_km: Optional[float] = None
    weeks: List[TaperWeekResponse] = []
    days_since_long_run: Optional[int] = None
    days_since_key_effort: Optional[int] = None


class PastBuildResponse(BaseModel):
    """A past race's build cut at the same days-before-race as today (R11.2)."""
    race: BlockRaceResponse
    result_vs_target_s: Optional[int] = None   # negative = faster than target; None for a DNF
    cut_date: str
    km: float
    runs: int
    long_runs: int
    longest_km: Optional[float] = None
    peak_week_km: Optional[float] = None
    consistency: Optional[ConsistencyResponse] = None
    taper: Optional[TaperResponse] = None


class EstimateSourceResponse(BaseModel):
    kind: str
    band: str
    distance_km: float
    time_s: int
    run_date: str
    age_days: int
    activity_id: Optional[int] = None
    name: Optional[str] = None
    segment: bool = False
    equivalent_s: int
    sets_estimate: bool = False


class BacktestRaceResponse(BaseModel):
    name: str
    race_date: str
    race_class: str
    actual_s: int
    predicted_s: Optional[int] = None
    error_s: Optional[int] = None
    error_pct: Optional[float] = None
    grade: Optional[str] = None


class BacktestSkipResponse(BaseModel):
    name: str
    race_date: str
    reason: str


class FinishEstimateResponse(BaseModel):
    """Finish-time range + evidence grade + live backtest (R11.7) — mirrors
    services.finish_estimate.FinishEstimate. A heuristic range, not a prediction."""
    state: str
    message: Optional[str] = None
    race_class: Optional[str] = None
    race_km: Optional[float] = None
    riegel_k: float
    window_from: Optional[str] = None
    window_to: Optional[str] = None
    estimate_s: Optional[int] = None
    low_s: Optional[int] = None
    high_s: Optional[int] = None
    band_pct: Optional[float] = None
    grade: Optional[str] = None
    grade_reasons: List[str] = []
    spread_pct: Optional[float] = None
    target_time_s: Optional[int] = None
    target_position: Optional[str] = None
    sources: List[EstimateSourceResponse] = []
    backtest: List[BacktestRaceResponse] = []
    backtest_skipped: List[BacktestSkipResponse] = []
    backtest_n: int = 0
    backtest_mean_abs_pct: Optional[float] = None
    backtest_max_abs_pct: Optional[float] = None
    coros_prediction_s: Optional[int] = None
    coros_captured_at: Optional[str] = None
    heuristic: bool = True


class LongRunFinishResponse(BaseModel):
    """One long run's finish from stored splits (R11.6). Moving clock; negative
    differences mean faster. Numbers are null when has_splits is false."""
    activity_id: Optional[int] = None
    run_date: str
    name: Optional[str] = None
    distance_km: float
    has_splits: bool
    moving_pace_s_per_km: Optional[int] = None
    first_half_pace_s_per_km: Optional[int] = None
    second_half_pace_s_per_km: Optional[int] = None
    split_diff_s_per_km: Optional[int] = None      # second - first; negative = negative split
    last_km_pace_s_per_km: Optional[int] = None
    last_km_vs_avg_s_per_km: Optional[int] = None  # last km - run average; negative = faster finish
    second_half_vs_target_s_per_km: Optional[int] = None


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
    long_run_finishes: List[LongRunFinishResponse] = []
    race_shoe: Optional[RaceShoeResponse] = None
    days_before_race: Optional[int] = None
    past_builds: List[PastBuildResponse] = []
    consistency: Optional[ConsistencyResponse] = None
    taper: Optional[TaperResponse] = None
    estimate: Optional[FinishEstimateResponse] = None
    heuristic: bool = True


# --- Race-block retrospective (R10.2) — mirrors services.race_advisor.BlockComparison ---

class BlockWeekResponse(BaseModel):
    offset: int                       # weeks relative to race week: 0 = race week, -1 = the week before
    week_start: str                   # ISO Monday
    km: float
    runs: int
    longest_km: float                 # 0.0 with no runs


class RaceBlockResponse(BaseModel):
    race: BlockRaceResponse
    block_start: str                  # ISO Monday
    block_end: str                    # ISO date, inclusive
    in_progress: bool                 # the race is today or ahead
    weeks: List[BlockWeekResponse] = []
    total_km: float
    runs: int
    avg_week_km: float
    peak_week: Optional[BlockWeekResponse] = None
    longest_run: Optional[ReadinessRunResponse] = None
    long_run_km: Optional[float] = None
    long_runs: int                    # runs at or above long_run_km
    steady_runs: int                  # runs training_trends.m_per_beat accepts
    median_m_per_beat: Optional[float] = None
    median_steady_pace_s_per_km: Optional[int] = None
    median_steady_hr: Optional[int] = None


class BlockComparisonResponse(BaseModel):
    """Race-block retrospective (R10.2): the blocks before every race of one class, oldest first."""
    as_of: str
    race_class: str
    block_weeks: int
    long_run_km: float
    blocks: List[RaceBlockResponse] = []
    heuristic: bool = True
