"""
Planned races API (P3.4). Thin router over app.services.races — the
countdown/pace derivation lives in the service so REST and MCP agree.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import PlannedRace
from app.models.schemas import (
    PlannedRaceCreate,
    PlannedRaceResponse,
    PlannedRaceUpdate,
)
from app.services import races as races_svc

router = APIRouter(prefix="/races", tags=["races"])


@router.get("", response_model=list[PlannedRaceResponse])
@router.get("/", response_model=list[PlannedRaceResponse])
def get_races(db: Session = Depends(get_db)):
    """All planned races, soonest first, with computed countdown + target pace."""
    return races_svc.list_races(db)


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


@router.delete("/{race_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_race(race_id: int, db: Session = Depends(get_db)):
    race = db.query(PlannedRace).filter(PlannedRace.id == race_id).first()
    if not race:
        raise HTTPException(status_code=404, detail=f"Race {race_id} not found")
    db.delete(race)
    db.commit()
