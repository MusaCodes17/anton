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

from app.models.models import Activity, Deal, OwnedShoe, PriceRecord, Shoe, ShoeNote, ShoeRun

CHECKPOINT_INTERVAL_KM = 100

# A shoe enters the "retirement pipeline" once it has burned this fraction of
# its user-set mileage_limit — the §4 attention threshold, shared by the Home
# shoe-alerts module and the /shoes lifecycle view so both agree.
RETIREMENT_THRESHOLD = 0.75


@dataclass
class LifetimeStats:
    lifetime_avg_pace: Optional[str]  # "M:SS/km"
    lifetime_avg_hr: Optional[int]
    total_runs: int


@dataclass
class PipelineEntry:
    """A shoe in the retirement pipeline, with its replacement-deal hint."""
    shoe: OwnedShoe
    pct: float                    # current_mileage / mileage_limit, 0..1+
    current_mileage: float
    mileage_limit: float
    replacement_deals: int        # active deals on a tracked shoe of the same type


@dataclass
class RunLogResult:
    run: ShoeRun          # the attribution row
    activity: Activity    # the canonical run record it points at
    shoe: OwnedShoe       # refreshed after commit
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
    Lifetime averages across every activity attributed to a shoe. Pace is
    already stored as seconds-per-km on the activity, so averaging is a plain
    mean; activities missing pace or HR are excluded from those averages but
    count toward total_runs.
    """
    acts = (
        db.query(Activity)
        .join(ShoeRun, ShoeRun.activity_id == Activity.id)
        .filter(ShoeRun.owned_shoe_id == owned_shoe_id)
        .all()
    )
    pace_seconds = [a.avg_pace_s_per_km for a in acts if a.avg_pace_s_per_km is not None]
    hrs = [a.avg_hr for a in acts if a.avg_hr is not None]
    return LifetimeStats(
        lifetime_avg_pace=seconds_to_pace(sum(pace_seconds) / len(pace_seconds)) if pace_seconds else None,
        lifetime_avg_hr=round(sum(hrs) / len(hrs)) if hrs else None,
        total_runs=len(acts),
    )


def cost_per_km(shoe: OwnedShoe) -> Optional[float]:
    """Purchase price divided by current mileage, rounded to 2dp. None if not computable."""
    if shoe.purchase_price and shoe.current_mileage > 0:
        return round(shoe.purchase_price / shoe.current_mileage, 2)
    return None


def active_deal_counts_by_type(db: Session) -> dict[str, int]:
    """
    Number of active deals per tracked-shoe `shoe_type`, keyed lowercase.

    A heuristic bridge between the rotation domain and the deals domain: there
    is no FK between owned_shoes and shoes, so a "replacement deal" is any
    active deal on a tracked Shoe of the same shoe_type.
    """
    counts: dict[str, int] = {}
    for shoe_type, cnt in (
        db.query(Shoe.shoe_type, func.count(Deal.id))
        .join(Deal, Deal.shoe_id == Shoe.id)
        .filter(Deal.is_active == True, Shoe.shoe_type.isnot(None))  # noqa: E712
        .group_by(Shoe.shoe_type)
        .all()
    ):
        counts[shoe_type.lower()] = cnt
    return counts


def retirement_pipeline(
    db: Session, threshold: float = RETIREMENT_THRESHOLD
) -> list[PipelineEntry]:
    """
    Active rotation shoes at/over ``threshold`` of their mileage_limit, worst
    (closest to or past the limit) first, each annotated with a count of
    matching replacement deals. Shoes without a mileage_limit are excluded —
    there is no limit to be a fraction of.
    """
    shoes = (
        db.query(OwnedShoe)
        .filter(OwnedShoe.status == "active", OwnedShoe.mileage_limit.isnot(None))
        .all()
    )
    counts = active_deal_counts_by_type(db)

    out: list[PipelineEntry] = []
    for s in shoes:
        if not s.mileage_limit:
            continue
        pct = s.current_mileage / s.mileage_limit
        if pct < threshold:
            continue
        out.append(PipelineEntry(
            shoe=s,
            pct=round(pct, 4),
            current_mileage=round(s.current_mileage, 1),
            mileage_limit=round(s.mileage_limit, 1),
            replacement_deals=counts.get(s.shoe_type.lower(), 0) if s.shoe_type else 0,
        ))

    out.sort(key=lambda e: e.pct, reverse=True)
    return out


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
    strava_activity_id: Optional[int] = None,
    avg_pace: Optional[str] = None,
    avg_hr: Optional[int] = None,
    notes: Optional[str] = None,
    increment_mileage: bool = True,
    commit: bool = True,
) -> RunLogResult:
    """
    Create a ShoeRun, increment the shoe's mileage, commit, and detect any
    100km checkpoint crossing.

    This is THE only code path that writes a ShoeRun — manual REST, MCP, COROS
    confirm, and Strava backfill all route here. Backfill passes
    ``increment_mileage=False`` (it applies its own reconciliation policy to the
    mileage afterward) and ``commit=False`` (it batches every write into one
    transaction it commits itself), so the invariant holds without the counter
    or transaction semantics that manual logging needs.

    Args:
        increment_mileage: add ``distance_km`` to the shoe's current_mileage.
            Set False when the caller manages mileage itself (Strava backfill).
        commit: commit the transaction. Set False to flush only (assigning
            ``run.id``) and leave the commit to the caller batching many writes.

    Raises LookupError if the shoe doesn't exist.
    """
    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
    if not shoe:
        raise LookupError(f"Owned shoe with id {owned_shoe_id} not found")

    old_mileage = shoe.current_mileage

    # Canonical activity first, then the attribution row that links it to a shoe
    # (§3 Phase-5). Pace comes in as "M:SS/km" and is stored as seconds; per-run
    # notes live on the activity's description.
    pace_s = pace_to_seconds(avg_pace) if avg_pace else None
    activity = Activity(
        source=source,
        activity_type="Run",
        run_date=run_date,
        distance_km=distance_km,
        avg_pace_s_per_km=int(pace_s) if pace_s is not None else None,
        avg_hr=avg_hr,
        coros_activity_id=coros_activity_id,
        strava_activity_id=strava_activity_id,
        description=notes,
    )
    db.add(activity)
    db.flush()  # assign activity.id

    run = ShoeRun(activity_id=activity.id, owned_shoe_id=owned_shoe_id)
    db.add(run)
    if increment_mileage:
        shoe.current_mileage += distance_km
    if commit:
        db.commit()
        db.refresh(run)
        db.refresh(shoe)
        db.refresh(activity)
    else:
        db.flush()  # assign run.id within the caller's open transaction

    cp = crossed_checkpoint(old_mileage, shoe.current_mileage)
    return RunLogResult(
        run=run,
        activity=activity,
        shoe=shoe,
        checkpoint_reached=cp is not None,
        checkpoint_km=cp,
    )


def delete_run(db: Session, run_id: int) -> OwnedShoe:
    """
    Delete a run attribution, subtract its distance back out of the parent
    shoe's mileage (floored at 0), commit, and return the refreshed shoe.

    The underlying activity is deleted too EXCEPT for source='strava' — the
    frozen bulk-export archive is preserved (deleting the attribution merely
    un-attributes that historical run from the shoe).

    Raises LookupError if the run or its parent shoe is missing.
    """
    run = db.query(ShoeRun).filter(ShoeRun.id == run_id).first()
    if not run:
        raise LookupError(f"Run with id {run_id} not found")

    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == run.owned_shoe_id).first()
    if not shoe:
        raise LookupError(f"Owned shoe for run {run_id} not found")

    activity = db.query(Activity).filter(Activity.id == run.activity_id).first()
    distance = (activity.distance_km if activity else 0.0) or 0.0

    db.delete(run)
    if activity is not None and activity.source != "strava":
        db.delete(activity)
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
