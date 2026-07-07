"""
API routes for managing shoes the user owns (personal rotation/mileage
tracking) — separate from app/routers/shoes.py, which is for deal tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, contains_eager
from typing import List, Optional

from app.database import get_db
from app.models import (
    OwnedShoe, OwnedShoeCreate, OwnedShoeUpdate, OwnedShoeResponse,
    ShoeRun, ShoeRunCreate, ShoeRunResponse, LogRunResponse,
    ShoeNote, ShoeNoteCreate, ShoeNoteResponse,
)
from app.models.models import Activity, Deal, Shoe
from app.services import rotation

router = APIRouter(prefix="/owned-shoes", tags=["owned-shoes"])


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
        rotation.attach_computed_fields(db, shoe)
    return shoes


@router.get("/rotation-overview")
def rotation_overview(db: Session = Depends(get_db)):
    """
    Retirement pipeline for the /shoes lifecycle view: active shoes at/over 75%
    of their mileage_limit, worst first, each with a replacement-deal count.

    Deliberately id-keyed and lightweight — the page already has full shoe
    objects from GET /owned-shoes and groups them by type client-side; this
    supplies only the server-computed pieces (pipeline membership + replacement
    hints), the same computation that backs the Home shoe-alerts module.
    """
    pipeline = rotation.retirement_pipeline(db)
    return {
        "threshold": rotation.RETIREMENT_THRESHOLD,
        "pipeline": [
            {
                "owned_shoe_id": e.shoe.id,
                "pct": e.pct,
                "current_mileage": e.current_mileage,
                "mileage_limit": e.mileage_limit,
                "replacement_deals": e.replacement_deals,
            }
            for e in pipeline
        ],
    }


@router.get("/{owned_shoe_id}", response_model=OwnedShoeResponse)
def get_owned_shoe(owned_shoe_id: int, db: Session = Depends(get_db)):
    """Get a specific owned shoe by ID"""
    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()

    if not shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe with id {owned_shoe_id} not found"
        )

    rotation.attach_computed_fields(db, shoe)
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
    return rotation.attach_computed_fields(db, db_shoe)


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
    return rotation.attach_computed_fields(db, db_shoe)


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


@router.post("/{owned_shoe_id}/log-run", response_model=LogRunResponse)
def log_run(owned_shoe_id: int, run: ShoeRunCreate, db: Session = Depends(get_db)):
    """
    Log a manual run against a shoe, accumulating its current_mileage.

    Flags checkpoint_reached when the new mileage crosses a 100km boundary
    (100, 200, 300...) that the previous mileage hadn't reached yet, so the
    frontend can prompt for a notes-journal entry. Whether that prompt has
    already been shown for a given checkpoint is tracked client-side.
    """
    try:
        result = rotation.log_run(
            db,
            owned_shoe_id,
            source="manual",
            **run.model_dump(),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return LogRunResponse(
        run_logged=True,
        updated_mileage=result.shoe.current_mileage,
        checkpoint_reached=result.checkpoint_reached,
        checkpoint_km=result.checkpoint_km,
        shoe=rotation.attach_computed_fields(db, result.shoe),
    )


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
        .join(Activity, ShoeRun.activity_id == Activity.id)
        .options(contains_eager(ShoeRun.activity))
        .filter(ShoeRun.owned_shoe_id == owned_shoe_id)
        .order_by(Activity.run_date.desc(), ShoeRun.created_at.desc())
        .all()
    )


@router.delete("/runs/{run_id}", response_model=OwnedShoeResponse)
def delete_shoe_run(run_id: int, db: Session = Depends(get_db)):
    """
    Delete a logged run, subtracting its distance back out of the parent
    shoe's current_mileage. Returns the updated shoe.
    """
    try:
        db_shoe = rotation.delete_run(db, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return rotation.attach_computed_fields(db, db_shoe)


@router.get("/{owned_shoe_id}/replacement-deals")
def get_replacement_deals(owned_shoe_id: int, db: Session = Depends(get_db)):
    """
    Active deals on shoes of the same type as this owned shoe, sorted by
    biggest discount first (max 6). Returns empty with a prompt message when
    shoe_type isn't set. Excludes the exact same model so we don't suggest
    "buy another copy of what you already own".
    """
    owned_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
    if not owned_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe with id {owned_shoe_id} not found",
        )

    if not owned_shoe.shoe_type:
        return {"shoe_type": None, "deals": [], "total": 0, "message": "Add a shoe type to see replacement suggestions"}

    deals = (
        db.query(Deal)
        .join(Deal.shoe)
        .filter(
            Deal.is_active == True,
            Deal.in_stock == True,
            Shoe.shoe_type == owned_shoe.shoe_type,
            func.lower(Shoe.model) != func.lower(owned_shoe.model),
        )
        .order_by(desc(Deal.savings_percent))
        .limit(6)
        .all()
    )

    deal_list = [
        {
            "id": d.id,
            "brand": d.shoe.brand,
            "model": d.shoe.model,
            "retailer": d.retailer.name,
            "current_price": d.current_price,
            "savings_percent": d.savings_percent,
            "savings_amount": d.savings_amount,
            "image_url": d.image_url,
            "product_url": d.product_url,
            "in_stock": d.in_stock,
            "sizes_available": d.sizes_available,  # JSON list, e.g. ["9","9.5"]; None pre-migration
        }
        for d in deals
    ]

    return {"shoe_type": owned_shoe.shoe_type, "deals": deal_list, "total": len(deal_list)}


@router.get("/{owned_shoe_id}/notes", response_model=List[ShoeNoteResponse])
def get_shoe_notes(owned_shoe_id: int, db: Session = Depends(get_db)):
    """List journal entries for a shoe, newest first"""
    db_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()

    if not db_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe with id {owned_shoe_id} not found"
        )

    return (
        db.query(ShoeNote)
        .filter(ShoeNote.owned_shoe_id == owned_shoe_id)
        .order_by(ShoeNote.created_at.desc())
        .all()
    )


@router.post("/{owned_shoe_id}/notes", response_model=ShoeNoteResponse, status_code=status.HTTP_201_CREATED)
def add_shoe_note(owned_shoe_id: int, note: ShoeNoteCreate, db: Session = Depends(get_db)):
    """Add a journal entry. mileage_at_note is set automatically from the shoe's current mileage."""
    try:
        return rotation.add_note(db, owned_shoe_id, note.body, note.triggered_by)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shoe_note(note_id: int, db: Session = Depends(get_db)):
    """Delete a journal entry"""
    db_note = db.query(ShoeNote).filter(ShoeNote.id == note_id).first()

    if not db_note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with id {note_id} not found"
        )

    db.delete(db_note)
    db.commit()
    return None
