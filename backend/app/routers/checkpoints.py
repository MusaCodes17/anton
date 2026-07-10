"""
Checkpoint-prompt state API (R2.6).

Persists which 100 km-checkpoint note prompts have already been shown per shoe,
moved off browser localStorage so a second device doesn't re-prompt. Thin
adapter over `services/checkpoints.py`; not folded into `owned_shoes` because it
is UI-prompt state, not a rotation/mileage fact (the checkpoint itself is
derived from `current_mileage`).
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.schemas import CheckpointPromptCreate, CheckpointPromptResponse
from app.services import checkpoints

router = APIRouter(prefix="/checkpoint-prompts", tags=["checkpoints"])


@router.get("", response_model=List[CheckpointPromptResponse])
@router.get("/", response_model=List[CheckpointPromptResponse])
def list_checkpoint_prompts(db: Session = Depends(get_db)):
    """Every (shoe, checkpoint_km) pair already prompted — the client fetches
    this set once and checks it before showing a checkpoint note prompt."""
    return checkpoints.list_prompted(db)


@router.post("", response_model=CheckpointPromptResponse)
@router.post("/", response_model=CheckpointPromptResponse)
def mark_checkpoint_prompted(payload: CheckpointPromptCreate, db: Session = Depends(get_db)):
    """Record that the checkpoint prompt was shown for a shoe. Idempotent."""
    return checkpoints.mark_prompted(
        db,
        owned_shoe_id=payload.owned_shoe_id,
        checkpoint_km=payload.checkpoint_km,
    )
