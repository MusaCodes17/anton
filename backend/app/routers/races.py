"""
Planned races API (P3.4). Thin router over app.services.races — the
countdown/pace derivation lives in the service so REST and MCP agree.
"""
from dataclasses import asdict
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import PlannedRace
from app.models.schemas import (
    PlannedRaceCreate,
    PlannedRaceLinkActivity,
    PlannedRaceResponse,
    PlannedRaceUpdate,
    RaceReadinessResponse,
)
from app.services import race_advisor
from app.services import races as races_svc

router = APIRouter(prefix="/races", tags=["races"])


@router.get("", response_model=list[PlannedRaceResponse])
@router.get("/", response_model=list[PlannedRaceResponse])
def get_races(db: Session = Depends(get_db)):
    """All planned races, soonest first, with computed countdown + target pace."""
    return races_svc.list_races(db)


@router.get("/readiness", response_model=RaceReadinessResponse)
def get_race_readiness(as_of: Optional[date] = None, db: Session = Depends(get_db)):
    """"Am I ready for my next race?" (R8.4.4) — a checklist with numbers, not a
    score. `as_of` defaults to today (Toronto); `has_race` False when no race is
    ahead. Same data as the MCP tool get_race_block_context's `readiness`."""
    return RaceReadinessResponse(**asdict(race_advisor.race_readiness(db, as_of=as_of)))


@router.post("", response_model=PlannedRaceResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=PlannedRaceResponse, status_code=status.HTTP_201_CREATED)
def create_race(payload: PlannedRaceCreate, db: Session = Depends(get_db)):
    race = PlannedRace(**payload.model_dump())
    db.add(race)
    db.commit()
    db.refresh(race)
    return races_svc.attach_derived(race)


@router.patch("/{race_id}", response_model=PlannedRaceResponse)
def update_race(race_id: int, payload: PlannedRaceUpdate, db: Session = Depends(get_db)):
    race = db.query(PlannedRace).filter(PlannedRace.id == race_id).first()
    if not race:
        raise HTTPException(status_code=404, detail=f"Race {race_id} not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(race, field, value)
    db.commit()
    db.refresh(race)
    return races_svc.attach_derived(race)


@router.post("/{race_id}/link-activity", response_model=PlannedRaceResponse)
def link_activity(race_id: int, payload: PlannedRaceLinkActivity, db: Session = Depends(get_db)):
    """Resolve a past race as run: link the activity that was the race (R8.3)."""
    try:
        race = races_svc.link_activity(db, race_id, payload.activity_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return races_svc.attach_derived(race)


@router.delete("/{race_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_race(race_id: int, db: Session = Depends(get_db)):
    race = db.query(PlannedRace).filter(PlannedRace.id == race_id).first()
    if not race:
        raise HTTPException(status_code=404, detail=f"Race {race_id} not found")
    db.delete(race)
    db.commit()
