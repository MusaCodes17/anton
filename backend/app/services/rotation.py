"""
Business logic for the personal shoe rotation domain.

This is the single authoritative implementation of run logging, checkpoint
detection, pace averaging, and related calculations. Routers and MCP tools
are thin adapters over these functions.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.models import (
    Activity, CheckpointPrompt, Deal, OwnedShoe, PlannedRace, PriceRecord,
    Shoe, ShoeNote, ShoeRun, StravaGearMapping,
)
# Pace formatting lives in the pure app.utils.pace module (R1.5c). Re-exported
# so existing callers (rotation.pace_to_seconds / rotation.seconds_to_pace) keep
# working; prefer importing from app.utils.pace directly in new code.
from app.utils.location import round_coord
from app.utils.pace import pace_to_seconds, seconds_to_pace  # noqa: F401
from app.utils.shoe_types import default_mileage_limit

CHECKPOINT_INTERVAL_KM = 100

# A shoe enters the "retirement pipeline" once it has burned this fraction of
# its user-set mileage_limit — the §4 attention threshold, shared by the Home
# shoe-alerts module and the /shoes lifecycle view so both agree.
RETIREMENT_THRESHOLD = 0.75

# R6.2 usage forecast. Recent weekly km = attributed distance over the last
# FORECAST_WEEKS full weeks / FORECAST_WEEKS (a heuristic — 6 weeks smooths one
# easy week without hiding a new training block). A shoe projected to hit its
# limit within RADAR_LOOKAHEAD_WEEKS joins the pipeline even below the 75%
# threshold: a heavy block can take a shoe from 70% to done before the
# threshold notices. The forecast widens the 75% band, it doesn't replace it.
FORECAST_WEEKS = 6
RADAR_LOOKAHEAD_WEEKS = 8

# forecast_status values
FORECAST_ON_TRACK = "on_track"   # has recent use → weeks_to_limit / projected date set
FORECAST_IDLE = "idle"           # no attributed km in the window → no date (not "never")
FORECAST_OVERDUE = "overdue"     # already at/over the limit → no date


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
    # R6.2 forecast (derived at read time, never stored — INV-7)
    forecast_status: str = FORECAST_IDLE
    weekly_km: float = 0.0                       # recent attributed km per week
    weeks_to_limit: Optional[float] = None       # None unless on_track
    projected_limit_date: Optional[str] = None   # ISO local date; None unless on_track


@dataclass
class RunLogResult:
    run: ShoeRun          # the attribution row
    activity: Activity    # the canonical run record it points at
    shoe: OwnedShoe       # refreshed after commit
    checkpoint_reached: bool
    checkpoint_km: Optional[int]
    # End-of-life advisory (MILEAGE_THRESHOLDS) crossed by this run, if any.
    threshold_crossed: Optional[int] = None
    threshold_message: Optional[str] = None


# End-of-life advisories (km). One table, computed once in log_run /
# reassign_attribution and carried on RunLogResult.threshold_crossed/_message to
# every surface (REST, MCP tools, COROS inbox) so they can't disagree
# (CLAUDE.md §1: correct numbers, once). Advice only — retirement is never enacted.
MILEAGE_THRESHOLDS: list[tuple[int, str]] = [
    (600, "approaching end of life — start thinking about replacement"),
    (700, "consider retiring soon — performance may be degrading"),
    (800, "past recommended limit — retire this shoe"),
]


def threshold_crossed_by(old_km: float, new_km: float) -> Optional[tuple[int, str]]:
    """The first MILEAGE_THRESHOLDS entry crossed going old_km -> new_km, else None.
    (A single run crossing two thresholds reports the lower one, as the MCP tool always has.)"""
    for km, message in MILEAGE_THRESHOLDS:
        if old_km < km <= new_km:
            return km, message
    return None


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


def compute_lifetime_stats_bulk(db: Session, owned_shoe_ids: list[int]) -> dict[int, LifetimeStats]:
    """
    ``compute_lifetime_stats`` for many shoes in ONE query. Same arithmetic
    (plain mean of pace, rounded mean of HR, total_runs counts every attributed
    activity), same ``Activity`` columns (not ShoeRun proxies; CLAUDE.md §6).
    Every requested id is present in the result (no runs -> empty stats).
    """
    rows = (
        db.query(ShoeRun.owned_shoe_id, Activity.avg_pace_s_per_km, Activity.avg_hr)
        .join(Activity, ShoeRun.activity_id == Activity.id)
        .filter(ShoeRun.owned_shoe_id.in_(owned_shoe_ids))
        .all()
    ) if owned_shoe_ids else []
    paces: dict[int, list] = {}
    hrs: dict[int, list] = {}
    totals: dict[int, int] = {}
    for sid, pace, hr in rows:
        totals[sid] = totals.get(sid, 0) + 1
        if pace is not None:
            paces.setdefault(sid, []).append(pace)
        if hr is not None:
            hrs.setdefault(sid, []).append(hr)
    out: dict[int, LifetimeStats] = {}
    for sid in owned_shoe_ids:
        p, h = paces.get(sid), hrs.get(sid)
        out[sid] = LifetimeStats(
            lifetime_avg_pace=seconds_to_pace(sum(p) / len(p)) if p else None,
            lifetime_avg_hr=round(sum(h) / len(h)) if h else None,
            total_runs=totals.get(sid, 0),
        )
    return out


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


def recent_weekly_km(
    db: Session, *, today: Optional[date] = None, weeks: int = FORECAST_WEEKS
) -> dict[int, float]:
    """
    Average attributed km per week over the last ``weeks`` weeks, keyed by
    owned_shoe_id (shoes with no attributed run in the window are absent).

    Queries ``Activity`` columns, not the ``ShoeRun`` proxies (which don't work
    in ``filter()``; CLAUDE.md §6). One grouped query for all shoes — no N+1.
    ``run_date`` is the America/Toronto local date, so ``today`` must be local.
    """
    today = today or date.today()
    since = today - timedelta(days=7 * weeks)
    rows = (
        db.query(ShoeRun.owned_shoe_id, func.sum(Activity.distance_km))
        .join(Activity, Activity.id == ShoeRun.activity_id)
        .filter(Activity.run_date > since, Activity.run_date <= today)
        .group_by(ShoeRun.owned_shoe_id)
        .all()
    )
    return {sid: (km or 0.0) / weeks for sid, km in rows}


def usage_forecast(
    shoe: OwnedShoe, weekly_km: float, *, today: Optional[date] = None
) -> tuple[str, Optional[float], Optional[str]]:
    """
    ``(status, weeks_to_limit, projected_limit_date)`` for one shoe.

    Pure. ``overdue`` once current_mileage >= limit; ``idle`` when there is no
    recent use (so no honest projection); otherwise remaining km / weekly km.
    """
    today = today or date.today()
    if shoe.mileage_limit and shoe.current_mileage >= shoe.mileage_limit:
        return FORECAST_OVERDUE, None, None
    if not shoe.mileage_limit or weekly_km <= 0:
        return FORECAST_IDLE, None, None
    weeks = (shoe.mileage_limit - shoe.current_mileage) / weekly_km
    return FORECAST_ON_TRACK, round(weeks, 1), (today + timedelta(days=round(weeks * 7))).isoformat()


def retirement_pipeline(
    db: Session,
    threshold: float = RETIREMENT_THRESHOLD,
    *,
    today: Optional[date] = None,
) -> list[PipelineEntry]:
    """
    Active rotation shoes at/over ``threshold`` of their mileage_limit — plus
    (R6.2) shoes projected to reach the limit within RADAR_LOOKAHEAD_WEEKS at
    their recent pace — worst (highest pct) first, each annotated with a count
    of matching replacement deals and the usage forecast. Shoes without a
    mileage_limit are excluded — there is no limit to be a fraction of.
    """
    shoes = (
        db.query(OwnedShoe)
        .filter(OwnedShoe.status == "active", OwnedShoe.mileage_limit.isnot(None))
        .all()
    )
    counts = active_deal_counts_by_type(db)
    weekly = recent_weekly_km(db, today=today)

    out: list[PipelineEntry] = []
    for s in shoes:
        if not s.mileage_limit:
            continue
        pct = s.current_mileage / s.mileage_limit
        wk = weekly.get(s.id, 0.0)
        status, weeks_to_limit, projected = usage_forecast(s, wk, today=today)
        on_radar = weeks_to_limit is not None and weeks_to_limit <= RADAR_LOOKAHEAD_WEEKS
        if pct < threshold and not on_radar:
            continue
        out.append(PipelineEntry(
            shoe=s,
            pct=round(pct, 4),
            current_mileage=round(s.current_mileage, 1),
            mileage_limit=round(s.mileage_limit, 1),
            replacement_deals=counts.get(s.shoe_type.lower(), 0) if s.shoe_type else 0,
            forecast_status=status,
            weekly_km=round(wk, 1),
            weeks_to_limit=weeks_to_limit,
            projected_limit_date=projected,
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


def attach_computed_fields(db: Session, shoe: OwnedShoe) -> OwnedShoe:
    """
    Attach response-only fields (image match, lifetime stats, cost/km) that
    aren't real columns onto an OwnedShoe instance, in place, and return it.

    This is the single home for owned-shoe response shaping — the REST routers
    (owned_shoes) and the COROS-sync router both project through it so every
    surface agrees on the derived numbers (CLAUDE.md §2). Derived-only: nothing
    here is persisted (INV-7).
    """
    shoe.matched_image_url = None if shoe.image_url else find_matched_image(db, shoe.brand, shoe.model)
    stats = compute_lifetime_stats(db, shoe.id)
    shoe.lifetime_avg_pace = stats.lifetime_avg_pace
    shoe.lifetime_avg_hr = stats.lifetime_avg_hr
    shoe.total_runs = stats.total_runs
    shoe.cost_per_km = cost_per_km(shoe)
    # Derived, never stored (INV-7): the type default the runner's own
    # mileage_limit is measured against, so the UI can say "recommended N km"
    # after the limit has been raised past it.
    shoe.recommended_limit_km = default_mileage_limit(shoe.shoe_type)
    return shoe


_ASCII_LOWER = {c: c + 32 for c in range(ord("A"), ord("Z") + 1)}


def _ascii_lower(text: str) -> str:
    """SQLite's lower() (and LIKE) fold ASCII only; Python's str.lower() folds
    Unicode too, so mirror SQLite exactly to keep matching identical."""
    return text.translate(_ASCII_LOWER)


def find_matched_images_bulk(db: Session, shoes: list[OwnedShoe]) -> dict[int, Optional[str]]:
    """
    ``find_matched_image`` for many shoes: one pass over price_records instead
    of one scan per shoe. The per-shoe SQL has no ORDER BY and SQLite plans it
    as a rowid-order SCAN, so "first match" == lowest price_records.id; this
    reproduces that by iterating in id order. Shoes whose brand/model contain
    LIKE wildcards (% or _) fall back to the per-shoe query, since a Python
    substring test would not match LIKE semantics there.
    """
    result: dict[int, Optional[str]] = {}
    pending: list[OwnedShoe] = []
    for sh in shoes:
        if sh.image_url:
            continue
        if any(ch in (sh.brand + sh.model) for ch in "%_"):
            result[sh.id] = find_matched_image(db, sh.brand, sh.model)
        else:
            pending.append(sh)
    if not pending:
        return result
    tracked = [
        (sid, _ascii_lower(b), _ascii_lower(m))
        for sid, b, m in db.query(Shoe.id, Shoe.brand, Shoe.model).all()
        if b is not None and m is not None
    ]
    keys = {(_ascii_lower(sh.brand), _ascii_lower(sh.model)) for sh in pending}
    matching_ids = {
        (bl, ml): {sid for sid, b, m in tracked if bl in b and ml in m} for bl, ml in keys
    }
    rows = [
        (sid, None if cw is None else _ascii_lower(cw), img)
        # Scrapes re-insert the same (shoe, colorway, image) every run; collapsing
        # to the earliest id per distinct triple keeps "first match by id"
        # identical while fetching ~1k rows instead of ~28k.
        for sid, cw, img, _first_id in db.query(
            PriceRecord.shoe_id, PriceRecord.colorway, PriceRecord.image_url, func.min(PriceRecord.id)
        )
        .filter(PriceRecord.image_url.isnot(None))
        .group_by(PriceRecord.shoe_id, PriceRecord.colorway, PriceRecord.image_url)
        .order_by(func.min(PriceRecord.id))
        .all()
    ]
    for sh in pending:
        key = (_ascii_lower(sh.brand), _ascii_lower(sh.model))
        ids, ml = matching_ids[key], key[1]
        result[sh.id] = next(
            (img for sid, cw, img in rows if (cw is not None and ml in cw) or sid in ids), None
        )
    return result


def attach_computed_fields_bulk(db: Session, shoes: list[OwnedShoe]) -> list[OwnedShoe]:
    """
    ``attach_computed_fields`` over a list with a constant number of queries
    (lifetime stats: 1; matched images: 2) — identical attributes and values.

    Personal-scale in-Python pass (CLAUDE.md §12): the per-shoe path cost
    ~410-580 ms CPU / 47 queries for 23 shoes on GET /api/owned-shoes (a
    lower(colorway) LIKE scan over ~28k price_records per shoe plus 1-2 stats
    queries per shoe). Single-shoe callers keep using ``attach_computed_fields``.
    """
    if not shoes:
        return shoes
    images = find_matched_images_bulk(db, shoes)
    stats = compute_lifetime_stats_bulk(db, [s.id for s in shoes])
    for shoe in shoes:
        shoe.matched_image_url = None if shoe.image_url else images.get(shoe.id)
        st = stats[shoe.id]
        shoe.lifetime_avg_pace = st.lifetime_avg_pace
        shoe.lifetime_avg_hr = st.lifetime_avg_hr
        shoe.total_runs = st.total_runs
        shoe.cost_per_km = cost_per_km(shoe)
        shoe.recommended_limit_km = default_mileage_limit(shoe.shoe_type)
    return shoes


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
    name: Optional[str] = None,
    elevation_gain_m: Optional[float] = None,
    moving_time_s: Optional[int] = None,
    elapsed_time_s: Optional[int] = None,
    avg_cadence: Optional[float] = None,
    calories: Optional[float] = None,
    training_load: Optional[float] = None,
    training_focus: Optional[str] = None,
    activity_tag: Optional[str] = None,
    start_lat: Optional[float] = None,
    start_lng: Optional[float] = None,
    location_label: Optional[str] = None,
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
        name..training_focus/activity_tag: optional richer activity fields
            (R2.7 T2) the COROS sync path now captures — all nullable, written
            straight onto the canonical Activity. Manual/Strava callers that
            don't have them simply omit them.
        start_lat/start_lng/location_label: optional start point (R5.4.1).
            Coordinates are rounded here via ``round_coord`` (~100 m) so every
            caller gets the privacy rule; only the rounded value is stored.
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
        name=name,
        run_date=run_date,
        distance_km=distance_km,
        avg_pace_s_per_km=int(pace_s) if pace_s is not None else None,
        avg_hr=avg_hr,
        elevation_gain_m=elevation_gain_m,
        moving_time_s=moving_time_s,
        elapsed_time_s=elapsed_time_s,
        avg_cadence=avg_cadence,
        calories=calories,
        training_load=training_load,
        training_focus=training_focus,
        activity_tag=activity_tag,
        start_lat=round_coord(start_lat),
        start_lng=round_coord(start_lng),
        location_label=location_label,
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
    th = threshold_crossed_by(old_mileage, shoe.current_mileage)
    return RunLogResult(
        run=run,
        activity=activity,
        shoe=shoe,
        checkpoint_reached=cp is not None,
        checkpoint_km=cp,
        threshold_crossed=th[0] if th else None,
        threshold_message=th[1] if th else None,
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


def delete_owned_shoe(db: Session, owned_shoe_id: int) -> None:
    """
    Delete an owned shoe, preserving data integrity across all FK references.

    - Non-strava Activities attributed to this shoe are deleted (INV-4: strava
      archive rows survive — only the ShoeRun attribution is removed).
    - PlannedRace.planned_shoe_id and StravaGearMapping.owned_shoe_id are
      nullable FKs: they are NULLed out rather than deleting the parent rows.
    - CheckpointPrompt records have a NOT NULL FK — they are deleted.
    - ShoeRun and ShoeNote rows are cascade-deleted by the ORM relationship.

    Raises LookupError if the shoe is not found.
    """
    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
    if not shoe:
        raise LookupError(f"Owned shoe with id {owned_shoe_id} not found")

    # Delete ShoeRun attributions explicitly, then their non-strava Activities.
    # The ShoeRun must go first: Activity.attribution has cascade="all,
    # delete-orphan" — deleting the Activity first would cascade the ShoeRun
    # and then the shoe's ORM cascade would try to delete it again (warning).
    # After flushing the run/activity deletes, expire the shoe so the
    # subsequent shoe cascade loads a fresh (empty) runs collection.
    for run in list(shoe.runs):
        activity = db.query(Activity).filter(Activity.id == run.activity_id).first()
        db.delete(run)
        if activity is not None and activity.source != "strava":
            db.delete(activity)
    db.flush()
    db.expire(shoe)

    # Nullable FK refs: NULL out rather than cascade-delete the referencing rows
    (db.query(PlannedRace)
       .filter(PlannedRace.planned_shoe_id == owned_shoe_id)
       .update({PlannedRace.planned_shoe_id: None}, synchronize_session="fetch"))
    (db.query(StravaGearMapping)
       .filter(StravaGearMapping.owned_shoe_id == owned_shoe_id)
       .update({StravaGearMapping.owned_shoe_id: None}, synchronize_session="fetch"))

    # NOT NULL FK with no cascade — delete before the shoe row disappears
    (db.query(CheckpointPrompt)
       .filter(CheckpointPrompt.owned_shoe_id == owned_shoe_id)
       .delete(synchronize_session="fetch"))

    db.delete(shoe)   # ORM cascade: ShoeRun, ShoeNote
    db.commit()


def reassign_attribution(db: Session, activity_id: int, new_shoe_id: int) -> RunLogResult:
    """
    Move an activity's shoe attribution to a different owned shoe, keeping the
    mileage ledger correct (INV-1): the old shoe loses this run's distance, the
    new shoe gains it. Creates the attribution if the activity was unattributed.

    Unlike delete_run this never touches the Activity row itself — only the
    ShoeRun attribution (which is UNIQUE per activity, INV-3) and the two shoes'
    counters. Idempotent no-op when `new_shoe_id` already owns the run.

    Raises LookupError if the activity or the target shoe is missing.
    Owns the commit.
    """
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise LookupError(f"Activity {activity_id} not found")
    new_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == new_shoe_id).first()
    if not new_shoe:
        raise LookupError(f"Owned shoe {new_shoe_id} not found")

    existing = db.query(ShoeRun).filter(ShoeRun.activity_id == activity_id).first()
    if existing and existing.owned_shoe_id == new_shoe_id:
        return RunLogResult(run=existing, activity=activity, shoe=new_shoe,
                            checkpoint_reached=False, checkpoint_km=None)

    dist = activity.distance_km or 0.0
    if existing:
        old_shoe = db.query(OwnedShoe).filter(OwnedShoe.id == existing.owned_shoe_id).first()
        if old_shoe:
            old_shoe.current_mileage = max(0.0, old_shoe.current_mileage - dist)
        db.delete(existing)
        db.flush()  # release the UNIQUE activity_id before inserting the new one

    old_new_mileage = new_shoe.current_mileage
    run = ShoeRun(activity_id=activity_id, owned_shoe_id=new_shoe_id)
    db.add(run)
    new_shoe.current_mileage += dist
    db.commit()
    db.refresh(run)
    db.refresh(new_shoe)
    db.refresh(activity)

    cp = crossed_checkpoint(old_new_mileage, new_shoe.current_mileage)
    th = threshold_crossed_by(old_new_mileage, new_shoe.current_mileage)
    return RunLogResult(run=run, activity=activity, shoe=new_shoe,
                        checkpoint_reached=cp is not None, checkpoint_km=cp,
                        threshold_crossed=th[0] if th else None,
                        threshold_message=th[1] if th else None)


def shoe_run_payload(sr: ShoeRun) -> dict:
    """
    Project an attribution row + its joined Activity into the `ShoeRunResponse`
    shape (the one place run fields are read off `sr.activity`; the old
    ShoeRun property proxies were retired 2026-10-10). Values are raw (dates,
    datetimes) -- validate through `ShoeRunResponse` to serialize. Callers that
    loop should eager-load `ShoeRun.activity` (N+1 otherwise).
    """
    a = sr.activity
    s = a.avg_pace_s_per_km if a else None
    return {
        "id": sr.id,
        "owned_shoe_id": sr.owned_shoe_id,
        "created_at": sr.created_at,
        "distance_km": a.distance_km if a else None,
        "run_date": a.run_date if a else None,
        "source": a.source if a else None,
        "avg_hr": a.avg_hr if a else None,
        "coros_activity_id": a.coros_activity_id if a else None,
        "notes": a.description if a else None,   # per-run notes live in activities.description
        "avg_pace": seconds_to_pace(s) if s is not None else None,
    }


def set_mileage_limit(db: Session, owned_shoe_id: int, limit_km: Optional[float]) -> OwnedShoe:
    """
    Set a shoe's retirement limit (km), or reset it to the shoe_type default
    when ``limit_km`` is None. Commits.

    The limit is the runner's call, not the app's: the type default is a
    heuristic, and a shoe that still feels good past it should stop nagging.
    The default stays visible as the derived ``recommended_limit_km`` so a
    raised limit never hides that the shoe is past the recommendation. Does not
    touch the mileage ledger (INV-1).

    Raises LookupError if the shoe doesn't exist; ValueError if limit_km <= 0.
    """
    if limit_km is not None and limit_km <= 0:
        raise ValueError("limit_km must be > 0")
    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
    if not shoe:
        raise LookupError(f"Owned shoe with id {owned_shoe_id} not found")
    shoe.mileage_limit = limit_km if limit_km is not None else default_mileage_limit(shoe.shoe_type)
    db.commit()
    db.refresh(shoe)
    return shoe


def adjust_mileage(db: Session, owned_shoe_id: int, new_mileage: float) -> OwnedShoe:
    """
    Manually override a shoe's current_mileage, recording the change as a
    journal note so the resulting drift from the ledger identity is auditable.

    This is the ONLY sanctioned way to set current_mileage to a value that is
    not `starting_mileage + Σ attributed distances` (INV-1). It exists for
    real-world corrections — a shoe worn on an untracked run, a bad import — and
    is the third blessed exception to the single-write-path rule (domain_model
    §4.5). The generic PUT /owned-shoes/{id} deliberately cannot touch the
    ledger (C1 fix, 2026-07-07); this endpoint is the one door, and the note it
    writes lets a later COROS/Strava reconciliation explain why the counter and
    the run sum disagree.

    Raises LookupError if the shoe doesn't exist; ValueError if new_mileage < 0.
    """
    if new_mileage < 0:
        raise ValueError("new_mileage must be >= 0")

    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
    if not shoe:
        raise LookupError(f"Owned shoe with id {owned_shoe_id} not found")

    old_mileage = shoe.current_mileage
    shoe.current_mileage = new_mileage
    db.add(ShoeNote(
        owned_shoe_id=owned_shoe_id,
        body=f"Mileage manually adjusted from {round(old_mileage, 1)} km to {round(new_mileage, 1)} km.",
        triggered_by="mileage_adjustment",
        mileage_at_note=new_mileage,
    ))
    db.commit()
    db.refresh(shoe)
    return shoe


def store_shoe_review(db: Session, owned_shoe_id: int, review_text: str) -> OwnedShoe:
    """
    Persist a review draft on an owned shoe (R3.3 review pipeline).

    Called by the MCP draft_shoe_review tool after sampling (auto-save) and
    by save_shoe_review (runner-initiated save after editing). Overwrites any
    previous draft — only one review per shoe is stored.

    Raises LookupError if the shoe doesn't exist.
    """
    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
    if not shoe:
        raise LookupError(f"Owned shoe with id {owned_shoe_id} not found")

    shoe.review_draft = review_text
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
