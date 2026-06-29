"""
API routes for managing shoes the user owns (personal rotation/mileage
tracking) — separate from app/routers/shoes.py, which is for deal tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import (
    OwnedShoe, OwnedShoeCreate, OwnedShoeUpdate, OwnedShoeResponse,
    ShoeRun, ShoeRunCreate, ShoeRunResponse, LogRunResponse,
    ShoeNote, ShoeNoteCreate, ShoeNoteResponse,
)
from app.models.models import Deal, PriceRecord, Shoe

router = APIRouter(prefix="/owned-shoes", tags=["owned-shoes"])

CHECKPOINT_INTERVAL_KM = 100


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


def _pace_to_seconds(pace: str) -> Optional[float]:
    """Parse a 'M:SS/km' pace string into total seconds. None if unparseable."""
    try:
        mins_str, secs_str = pace.split('/')[0].strip().split(':')
        return int(mins_str) * 60 + int(secs_str)
    except (ValueError, AttributeError):
        return None


def _seconds_to_pace(seconds: float) -> str:
    """Format total seconds back into a 'M:SS/km' pace string."""
    total = round(seconds)
    mins, secs = divmod(total, 60)
    return f"{mins}:{secs:02d}/km"


def _compute_lifetime_stats(db: Session, owned_shoe_id: int) -> dict:
    """
    Lifetime averages across every run logged against a shoe. Pace strings
    can't be averaged directly (e.g. averaging "3:50/km" and "4:10/km" as
    text means nothing) — each is converted to seconds first, averaged, then
    formatted back. Runs missing a pace/HR are excluded from that average
    but still count toward total_runs.
    """
    runs = db.query(ShoeRun).filter(ShoeRun.owned_shoe_id == owned_shoe_id).all()
    pace_seconds = [s for s in (_pace_to_seconds(r.avg_pace) for r in runs if r.avg_pace) if s is not None]
    hrs = [r.avg_hr for r in runs if r.avg_hr is not None]
    return {
        "lifetime_avg_pace": _seconds_to_pace(sum(pace_seconds) / len(pace_seconds)) if pace_seconds else None,
        "lifetime_avg_hr": round(sum(hrs) / len(hrs)) if hrs else None,
        "total_runs": len(runs),
    }


def _attach_computed_fields(db: Session, shoe: OwnedShoe) -> OwnedShoe:
    """Attach the response-only fields (image match, lifetime stats, cost/km) that aren't real columns."""
    shoe.matched_image_url = None if shoe.image_url else _find_matched_image(db, shoe.brand, shoe.model)
    stats = _compute_lifetime_stats(db, shoe.id)
    shoe.lifetime_avg_pace = stats["lifetime_avg_pace"]
    shoe.lifetime_avg_hr = stats["lifetime_avg_hr"]
    shoe.total_runs = stats["total_runs"]
    shoe.cost_per_km = (
        round(shoe.purchase_price / shoe.current_mileage, 2)
        if shoe.purchase_price and shoe.current_mileage > 0
        else None
    )
    return shoe


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
        _attach_computed_fields(db, shoe)
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

    _attach_computed_fields(db, shoe)
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
    return _attach_computed_fields(db, db_shoe)


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
    return _attach_computed_fields(db, db_shoe)


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
    db_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()

    if not db_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe with id {owned_shoe_id} not found"
        )

    old_mileage = db_shoe.current_mileage
    db_run = ShoeRun(owned_shoe_id=owned_shoe_id, source="manual", **run.model_dump())
    db.add(db_run)
    db_shoe.current_mileage += run.distance_km
    db.commit()
    db.refresh(db_shoe)

    old_checkpoint = int(old_mileage // CHECKPOINT_INTERVAL_KM) * CHECKPOINT_INTERVAL_KM
    new_checkpoint = int(db_shoe.current_mileage // CHECKPOINT_INTERVAL_KM) * CHECKPOINT_INTERVAL_KM
    checkpoint_reached = new_checkpoint > old_checkpoint and new_checkpoint > 0

    return LogRunResponse(
        run_logged=True,
        updated_mileage=db_shoe.current_mileage,
        checkpoint_reached=checkpoint_reached,
        checkpoint_km=new_checkpoint if checkpoint_reached else None,
        shoe=_attach_computed_fields(db, db_shoe),
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
        .filter(ShoeRun.owned_shoe_id == owned_shoe_id)
        .order_by(ShoeRun.run_date.desc(), ShoeRun.created_at.desc())
        .all()
    )


@router.delete("/runs/{run_id}", response_model=OwnedShoeResponse)
def delete_shoe_run(run_id: int, db: Session = Depends(get_db)):
    """
    Delete a logged run, subtracting its distance back out of the parent
    shoe's current_mileage. Returns the updated shoe.
    """
    run = db.query(ShoeRun).filter(ShoeRun.id == run_id).first()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run with id {run_id} not found"
        )

    db_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == run.owned_shoe_id).first()
    distance = run.distance_km
    db.delete(run)

    if db_shoe:
        db_shoe.current_mileage = max(0, db_shoe.current_mileage - distance)
    db.commit()

    if not db_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe for run {run_id} not found"
        )

    db.refresh(db_shoe)
    return _attach_computed_fields(db, db_shoe)


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
    db_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()

    if not db_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Owned shoe with id {owned_shoe_id} not found"
        )

    db_note = ShoeNote(
        owned_shoe_id=owned_shoe_id,
        body=note.body,
        triggered_by=note.triggered_by,
        mileage_at_note=db_shoe.current_mileage,
    )
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note


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
