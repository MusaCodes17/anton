"""
Runner preferences API (R6.3) — thin adapter over `services/settings.py`.

Currently the shoe-size preference, the "hide other sizes" toggle for the
Deals page, and the Training-page section layout (order + hidden sections).
A preference is reversible config, not a data mutation, so it is not
confirmation-gated (C9) — same stance as the scrape schedule.

The training layout is UI-only presentation state, so it has no MCP
counterpart: no tool or resource exposes it, and the MCP surface never reads
or writes it. It is served here so phone and laptop render the same layout.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import settings as settings_svc

router = APIRouter(prefix="/preferences", tags=["preferences"])


class PreferencesUpdate(BaseModel):
    preferred_size: Optional[str] = None   # "" / null clears it
    hide_other_sizes: bool = False


class TrainingLayoutUpdate(BaseModel):
    order: list[str]
    hidden: list[str] = []


def _response(db: Session) -> dict:
    size = settings_svc.get_preferred_size(db)
    return {
        "preferred_size": size,
        "hide_other_sizes": settings_svc.get_hide_other_sizes(db),
        "training_layout": settings_svc.get_training_layout(db),
    }


@router.get("", response_model=dict)
@router.get("/", response_model=dict)
def get_preferences(db: Session = Depends(get_db)):
    return _response(db)


@router.put("", response_model=dict)
@router.put("/", response_model=dict)
def update_preferences(body: PreferencesUpdate, db: Session = Depends(get_db)):
    try:
        settings_svc.set_preferred_size(db, body.preferred_size)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    settings_svc.set_hide_other_sizes(db, body.hide_other_sizes)
    db.commit()
    return _response(db)


@router.put("/training-layout", response_model=dict)
def update_training_layout(body: TrainingLayoutUpdate, db: Session = Depends(get_db)):
    """
    Replace the Training-page section layout. Does not touch the size fields,
    and `PUT /preferences` does not touch the layout.
    """
    try:
        settings_svc.set_training_layout(db, order=body.order, hidden=body.hidden)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    db.commit()
    return _response(db)
