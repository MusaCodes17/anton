"""
Pydantic schemas for Son of Anton chat persistence and the 100 km checkpoint
prompt. Re-exported from `app.models.schemas`.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Chat persistence (R2.6) ─────────────────────────────────────────────────

class ConversationUpsert(BaseModel):
    """Create-or-replace payload for a Son of Anton conversation. Mirrors the
    old whole-conversation localStorage save — the client PUTs the full state
    on stream-end. Message arrays are opaque JSON (UI + LLM shapes)."""
    title: Optional[str] = None
    model: Optional[str] = None
    display_messages: List = Field(default_factory=list)
    api_messages: List = Field(default_factory=list)


class ConversationSummary(BaseModel):
    """List-panel projection — no message bodies, just what the sidebar needs."""
    id: str
    title: Optional[str] = None
    model: Optional[str] = None
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationResponse(BaseModel):
    """A full conversation, including both message arrays, for load-on-select."""
    id: str
    title: Optional[str] = None
    model: Optional[str] = None
    display_messages: List = Field(default_factory=list)
    api_messages: List = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CheckpointPromptCreate(BaseModel):
    """Mark the 100 km-checkpoint prompt as shown for a shoe (idempotent)."""
    owned_shoe_id: int
    checkpoint_km: int


class CheckpointPromptResponse(BaseModel):
    owned_shoe_id: int
    checkpoint_km: int

    class Config:
        from_attributes = True
