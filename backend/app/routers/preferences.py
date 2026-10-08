"""
Runner preferences API (R6.3) — thin adapter over `services/settings.py`.

Currently the shoe-size preference and the "hide other sizes" toggle for the
Deals page. A preference is reversible config, not a data mutation, so it is
not confirmation-gated (C9) — same stance as the scrape schedule.
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


def _response(db: Session) -> dict:
    size = settings_svc.get_preferred_size(db)
    return {
        "preferred_size": size,
        "hide_other_sizes": settings_svc.get_hide_other_sizes(db),
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
