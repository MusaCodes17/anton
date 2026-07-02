"""
Business logic for the personal shoe rotation domain.

This is the single authoritative implementation of run logging, checkpoint
detection, pace averaging, and related calculations. Routers and MCP tools
are thin adapters over these functions.
"""
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.models import OwnedShoe, PriceRecord, Shoe, ShoeNote, ShoeRun

CHECKPOINT_INTERVAL_KM = 100


@dataclass
class LifetimeStats:
    lifetime_avg_pace: Optional[str]  # "M:SS/km"
    lifetime_avg_hr: Optional[int]
    total_runs: int


@dataclass
class RunLogResult:
    run: ShoeRun
    shoe: OwnedShoe        # refreshed after commit
    checkpoint_reached: bool
    checkpoint_km: Optional[int]


def pace_to_seconds(pace: str) -> Optional[float]:
    """Parse a 'M:SS/km' pace string into total seconds. Returns None if unparseable."""
    try:
        mins_str, secs_str = pace.split('/')[0].strip().split(':')
        return int(mins_str) * 60 + int(secs_str)
    except (ValueError, AttributeError):
        return None


def seconds_to_pace(seconds: float) -> str:
    """Format total seconds back into a 'M:SS/km' pace string."""
    total = round(seconds)
    mins, secs = divmod(total, 60)
    return f"{mins}:{secs:02d}/km"


def crossed_checkpoint(
    old_km: float,
    new_km: float,
    interval: int = CHECKPOINT_INTERVAL_KM,
) -> Optional[int]:
    """
    Return the checkpoint value crossed (e.g. 300) if the mileage moved from
    below it to at-or-above it, otherwise None.

    Handles only the lowest crossed checkpoint — callers that need to detect
    multiple crossings in one run should call this in a loop or check
    floor(new/interval) - floor(old/interval) > 1.
    """
    old_cp = int(old_km // interval) * interval
    new_cp = int(new_km // interval) * interval
    if new_cp > old_cp and new_cp > 0:
        return new_cp
    return None


def compute_lifetime_stats(db: Session, owned_shoe_id: int) -> LifetimeStats:
    """
    Lifetime averages across every run logged against a shoe. Pace strings are
    converted to seconds before averaging to avoid string-averaging nonsense;
    runs missing pace or HR are excluded from those averages but count toward
    total_runs.
    """
    runs = db.query(ShoeRun).filter(ShoeRun.owned_shoe_id == owned_shoe_id).all()
    pace_seconds = [
        s for s in (pace_to_seconds(r.avg_pace) for r in runs if r.avg_pace)
        if s is not None
    ]
    hrs = [r.avg_hr for r in runs if r.avg_hr is not None]
    return LifetimeStats(
        lifetime_avg_pace=seconds_to_pace(sum(pace_seconds) / len(pace_seconds)) if pace_seconds else None,
        lifetime_avg_hr=round(sum(hrs) / len(hrs)) if hrs else None,
        total_runs=len(runs),
    )


def cost_per_km(shoe: OwnedShoe) -> Optional[float]:
    """Purchase price divided by current mileage, rounded to 2dp. None if not computable."""
    if shoe.purchase_price and shoe.current_mileage > 0:
        return round(shoe.purchase_price / shoe.current_mileage, 2)
    return None


def find_matched_image(db: Session, brand: str, model: str) -> Optional[str]:
    """
    Best-effort lookup of a product image from scraped price_records. Matches
    by colorway text or via the linked tracked Shoe's brand/model (both
    case-insensitive substring). No FK between owned_shoes and shoes — this is
    a heuristic.
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


def log_run(
    db: Session,
    owned_shoe_id: int,
    *,
    distance_km: float,
    run_date: date,
    source: str = "manual",
    coros_activity_id: Optional[str] = None,
    avg_pace: Optional[str] = None,
    avg_hr: Optional[int] = None,
    notes: Optional[str] = None,
) -> RunLogResult:
    """
    Create a ShoeRun, increment the shoe's mileage, commit, and detect any
    100km checkpoint crossing.

    This is THE only code path that writes a ShoeRun — manual REST, MCP, and
    COROS confirm all route here (after Task D).

    Raises LookupError if the shoe doesn't exist.
    """
    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
    if not shoe:
        raise LookupError(f"Owned shoe with id {owned_shoe_id} not found")

    old_mileage = shoe.current_mileage
    run = ShoeRun(
        owned_shoe_id=owned_shoe_id,
        distance_km=distance_km,
        run_date=run_date,
        source=source,
        coros_activity_id=coros_activity_id,
        avg_pace=avg_pace,
        avg_hr=avg_hr,
        notes=notes,
    )
    db.add(run)
    shoe.current_mileage += distance_km
    db.commit()
    db.refresh(run)
    db.refresh(shoe)

    cp = crossed_checkpoint(old_mileage, shoe.current_mileage)
    return RunLogResult(
        run=run,
        shoe=shoe,
        checkpoint_reached=cp is not None,
        checkpoint_km=cp,
    )


def delete_run(db: Session, run_id: int) -> OwnedShoe:
    """
    Delete a logged run, subtract its distance back out of the parent shoe's
    mileage (floored at 0), commit, and return the refreshed shoe.

    Raises LookupError if the run or its parent shoe is missing.
    """
    run = db.query(ShoeRun).filter(ShoeRun.id == run_id).first()
    if not run:
        raise LookupError(f"Run with id {run_id} not found")

    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == run.owned_shoe_id).first()
    if not shoe:
        raise LookupError(f"Owned shoe for run {run_id} not found")

    distance = run.distance_km
    db.delete(run)
    shoe.current_mileage = max(0.0, shoe.current_mileage - distance)
    db.commit()
    db.refresh(shoe)
    return shoe


def add_note(
    db: Session,
    owned_shoe_id: int,
    body: str,
    triggered_by: str = "manual",
) -> ShoeNote:
    """
    Add a journal entry. mileage_at_note is captured server-side from the
    shoe's current mileage at write time.

    Raises LookupError if the shoe doesn't exist.
    """
    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
    if not shoe:
        raise LookupError(f"Owned shoe with id {owned_shoe_id} not found")

    note = ShoeNote(
        owned_shoe_id=owned_shoe_id,
        body=body,
        triggered_by=triggered_by,
        mileage_at_note=shoe.current_mileage,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note
