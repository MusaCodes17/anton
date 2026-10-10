"""
Pydantic schemas for API request/response validation.

Split by domain into one module per area (deals, rotation, training, chat,
settings), with shared validators in `_common`. `from app.models.schemas import X`
remains the import path for every schema and helper; the submodules are an
implementation detail.
"""

from app.models.schemas._common import (
    OWNED_SHOE_STATUSES,
    validate_optional_shoe_type,
    validate_owned_shoe_status,
)

from app.models.schemas.deals import (
    DashboardStats,
    DealBase,
    DealCreate,
    DealResponse,
    PriceRecordBase,
    PriceRecordCreate,
    PriceRecordResponse,
    PromoCodeBase,
    PromoCodeCreate,
    PromoCodeResponse,
    RetailerBase,
    RetailerCreate,
    RetailerResponse,
    RetailerUpdate,
    ScrapeRequest,
    ScrapeResult,
    ShoeBase,
    ShoeCreate,
    ShoeResponse,
    ShoeTestRequest,
    ShoeUpdate,
)

from app.models.schemas.rotation import (
    LogRunResponse,
    MileageAdjust,
    OwnedShoeBase,
    OwnedShoeCreate,
    OwnedShoeResponse,
    OwnedShoeUpdate,
    ShoeNoteCreate,
    ShoeNoteResponse,
    ShoeReviewUpdate,
    ShoeRunBase,
    ShoeRunCreate,
    ShoeRunResponse,
)

from app.models.schemas.training import (
    PlannedRaceBase,
    PlannedRaceCreate,
    PlannedRaceLinkActivity,
    PlannedRaceResponse,
    PlannedRaceUpdate,
    PlannedShoeBrief,
    RaceReadinessResponse,
    ReadinessChecklistItem,
    ReadinessEffortResponse,
    ReadinessRaceResponse,
    ReadinessRunResponse,
    ReadinessWeekResponse,
)

from app.models.schemas.chat import (
    CheckpointPromptCreate,
    CheckpointPromptResponse,
    ConversationResponse,
    ConversationSummary,
    ConversationUpsert,
)

from app.models.schemas.settings import (
    ScheduleUpdate,
)

from app.models.schemas.watchlist import (
    LastSeenPrice,
    WatchlistDeal,
    WatchlistItem,
)
