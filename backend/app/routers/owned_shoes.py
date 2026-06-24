"""
API routes for managing shoes the user owns (personal rotation/mileage
tracking) — separate from app/routers/shoes.py, which is for deal tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import (
    OwnedShoe, OwnedShoeCreate, OwnedShoeUpdate, OwnedShoeResponse,
    ShoeRun, ShoeRunCreate, ShoeRunResponse,
)
from app.models.models import PriceRecord, Shoe

router = APIRouter(prefix="/owned-shoes", tags=["owned-shoes"])


def _find_matched_image(db: Session, brand: str, model: str) -> Optional[str]:
    """
    Best-effort lookup of a product image for an owned shoe from scraped
    price_records — matches by colorway text or by the linked tracked Shoe's
    brand/model, both case-insensitive substring matches. There's no FK
    between owned_shoes and shoes, so this is a heuristic, not a join.
    """
    model_l = model.lower()
    brand_l = brand.lower()
    match = (
        db.query(PriceRecord.image_url)
        .filter(PriceRecord.image_url.isnot(None))
        .filter(
            or_(
                func.lower(PriceRecord.colorway).like(f"%{model_l}%"),
                PriceRecord.shoe_id.in_(
                    db.query(Shoe.id).filter(
                        func.lower(Shoe.brand).like(f"%{brand_l}%"),
                        func.lower(Shoe.model).like(f"%{model_l}%"),
                    )
                ),
            )
        )
        .first()
    )
    return match[0] if match else None


@router.get("/", response_model=List[OwnedShoeResponse])
def get_owned_shoes(status_filter: str = None, db: Session = Depends(get_db)):
    """
    List shoes in the personal rotation, optionally filtered by status
    (active | retired | for_sale).
    """
    query = db.query(OwnedShoe)
    if status_filter:
        query = query.filter(OwnedShoe.status == status_filter)
    shoes = query.order_by(OwnedShoe.created_at.desc()).all()
    for shoe in shoes:
        shoe.matched_image_url = None if shoe.image_url else _find_matched_image(db, shoe.brand, shoe.model)
    return shoes


@router.get("/{owned_shoe_id}", response_model=OwnedShoeResponse)
def get_owned_shoe(owned_shoe_id: int, db: Session = Depends(get_db)):
    """Get a specific owned shoe by ID"""
    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()

    if not shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe with id {owned_shoe_id} not found"
        )

    shoe.matched_image_url = None if shoe.image_url else _find_matched_image(db, shoe.brand, shoe.model)
    return shoe


@router.post("/", response_model=OwnedShoeResponse, status_code=status.HTTP_201_CREATED)
def create_owned_shoe(shoe: OwnedShoeCreate, db: Session = Depends(get_db)):
    """
    Add a shoe to the personal rotation. current_mileage starts equal to
    starting_mileage (allows adding shoes already partially worn).
    """
    db_shoe = OwnedShoe(**shoe.model_dump())
    db_shoe.current_mileage = db_shoe.starting_mileage
    db.add(db_shoe)
    db.commit()
    db.refresh(db_shoe)
    return db_shoe


@router.put("/{owned_shoe_id}", response_model=OwnedShoeResponse)
def update_owned_shoe(owned_shoe_id: int, shoe_update: OwnedShoeUpdate, db: Session = Depends(get_db)):
    """Update an owned shoe's mileage, notes, status, or other fields"""
    db_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()

    if not db_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe with id {owned_shoe_id} not found"
        )

    update_data = shoe_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_shoe, field, value)

    db.commit()
    db.refresh(db_shoe)
    return db_shoe


@router.delete("/{owned_shoe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owned_shoe(owned_shoe_id: int, db: Session = Depends(get_db)):
    """Delete an owned shoe and its run history"""
    db_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()

    if not db_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe with id {owned_shoe_id} not found"
        )

    db.delete(db_shoe)
    db.commit()
    return None


@router.post("/{owned_shoe_id}/log-run", response_model=OwnedShoeResponse)
def log_run(owned_shoe_id: int, run: ShoeRunCreate, db: Session = Depends(get_db)):
    """Log a manual run against a shoe, accumulating its current_mileage"""
    db_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()

    if not db_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe with id {owned_shoe_id} not found"
        )

    db_run = ShoeRun(owned_shoe_id=owned_shoe_id, source="manual", **run.model_dump())
    db.add(db_run)
    db_shoe.current_mileage += run.distance_km
    db.commit()
    db.refresh(db_shoe)
    return db_shoe


@router.get("/{owned_shoe_id}/runs", response_model=List[ShoeRunResponse])
def get_shoe_runs(owned_shoe_id: int, db: Session = Depends(get_db)):
    """Get run history for a shoe, newest first"""
    db_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()

    if not db_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe with id {owned_shoe_id} not found"
        )

    return (
        db.query(ShoeRun)
        .filter(ShoeRun.owned_shoe_id == owned_shoe_id)
        .order_by(ShoeRun.run_date.desc(), ShoeRun.created_at.desc())
        .all()
    )
