"""
Checkpoint-prompt state (R2.6).

Remembers that the 100 km-checkpoint note prompt was already shown for a shoe,
so it isn't shown again — moved off browser localStorage so a second device
doesn't re-prompt at the same checkpoint. This is UI-state persistence, not a
mileage-ledger fact: the checkpoint itself is derived from `current_mileage`
(rotation), this store only records that we asked.

Owns the writes to `checkpoint_prompts`; the (shoe, km) pair is unique so
`mark_prompted` is idempotent.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import CheckpointPrompt


def list_prompted(db: Session) -> list[dict]:
    """Every (shoe, checkpoint_km) pair already prompted — the set the client
    checks before showing a checkpoint note prompt."""
    rows = db.query(CheckpointPrompt).all()
    return [
        {"owned_shoe_id": r.owned_shoe_id, "checkpoint_km": r.checkpoint_km}
        for r in rows
    ]


def mark_prompted(db: Session, *, owned_shoe_id: int, checkpoint_km: int) -> CheckpointPrompt:
    """Record that the checkpoint prompt was shown for a shoe. Idempotent —
    an existing (shoe, km) row is returned unchanged rather than duplicated."""
    existing = (
        db.query(CheckpointPrompt)
        .filter(
            CheckpointPrompt.owned_shoe_id == owned_shoe_id,
            CheckpointPrompt.checkpoint_km == checkpoint_km,
        )
        .first()
    )
    if existing is not None:
        return existing
    prompt = CheckpointPrompt(owned_shoe_id=owned_shoe_id, checkpoint_km=checkpoint_km)
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt
