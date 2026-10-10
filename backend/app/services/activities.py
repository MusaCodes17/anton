"""
Unified activity feed (§3 Phase-3a, now over the canonical `activities` table).

As of §3 Phase-5 there is ONE run store: the `activities` table. Every physical
run — Strava export, COROS sync, manual log — is a single Activity row,
distinguished by `source`; `shoe_runs` is a pure attribution row linking an
activity to the owned shoe it was run in. The old two-store dedup-by-link join
is gone: each run already appears exactly once.

This service still exists as the read seam the whole app (web + MCP + future
mobile) goes through, so callers (`strava_stats`, `home`, routers) are
unchanged — `UnifiedActivity` keeps its shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Activity, OwnedShoe, ShoeRun
from app.services import rotation


@dataclass
class UnifiedShoe:
    id: int
    brand: str
    model: str
    nickname: Optional[str] = None


@dataclass
class UnifiedActivity:
    date: date
    distance_km: float
    source: str                         # "strava" | "coros" | "manual"
    moving_time_s: Optional[int] = None
    avg_pace: Optional[str] = None      # "M:SS/km"
    avg_pace_s_per_km: Optional[int] = None
    avg_hr: Optional[int] = None
    elevation_m: Optional[float] = None
    name: Optional[str] = None
    elapsed_time_s: Optional[int] = None   # the records clock (R8.1)
    activity_tag: Optional[str] = None     # controlled vocab; drives PB eligibility (R2.7 T3)
    activity_id: Optional[int] = None      # canonical Activity id (for edit/detail — R2.7 T6)
    shoe: Optional[UnifiedShoe] = None
    strava_activity_id: Optional[int] = None
    shoe_run_id: Optional[int] = None

    @property
    def _sort_key(self):
        # Deterministic tiebreak so pagination is stable when two runs share a
        # date (which is common — Strava stores date only, no time here).
        return (self.date, self.strava_activity_id or 0, self.shoe_run_id or 0)


def _effective_moving_s(a: UnifiedActivity) -> Optional[float]:
    """Seconds used for distance-weighted pace: real moving time when we have
    it (Strava), else reconstructed from the run's average pace."""
    if a.moving_time_s and a.distance_km:
        return float(a.moving_time_s)
    if a.avg_pace_s_per_km and a.distance_km:
        return a.avg_pace_s_per_km * a.distance_km
    return None


def _row_to_unified(row) -> UnifiedActivity:
    """Map one column-only result row (see the `unified_activities` query for the
    exact column list, `a_*` = activities, `s_*` = owned_shoes, `shoe_run_id` =
    shoe_runs.id) to the `UnifiedActivity` projection. Takes a SQLAlchemy `Row`
    (attribute access), so it never touches ORM entities."""
    pace_s = row.avg_pace_s_per_km
    return UnifiedActivity(
        date=row.run_date,
        distance_km=row.distance_km or 0.0,
        source=row.source,
        moving_time_s=row.moving_time_s,
        avg_pace=rotation.seconds_to_pace(pace_s) if pace_s else None,
        avg_pace_s_per_km=pace_s,
        avg_hr=row.avg_hr,
        elevation_m=row.elevation_gain_m,
        name=row.name,
        elapsed_time_s=row.elapsed_time_s,
        activity_tag=row.activity_tag,
        activity_id=row.id,
        shoe=(UnifiedShoe(id=row.s_id, brand=row.s_brand, model=row.s_model, nickname=row.s_nickname)
              if row.s_id is not None else None),
        strava_activity_id=row.strava_activity_id,
        shoe_run_id=row.shoe_run_id,
    )


def unified_activities(
    db: Session,
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    shoe_id: Optional[int] = None,
    min_distance_km: Optional[float] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[UnifiedActivity]:
    """
    The unioned run feed, newest first, with optional filters and stable
    limit/offset pagination.

    R2.3: the filters, ordering, and limit/offset are pushed into a single
    indexed SQL query (LEFT JOIN through `shoe_runs` → `owned_shoes` for the
    optional attribution) instead of loading every activity and reducing in
    Python — the seam's shape (`UnifiedActivity`, this signature) is unchanged,
    so every caller is untouched. Index: `ix_activities_type_run_date`
    (activity_type, run_date) serves the base filter + newest-first order.
    year/month use `strftime` (SQLite; the app is SQLite-only) so `month=6`
    still matches June across all years; the ORDER BY tiebreak coalesces the
    two nullable id columns to 0 to reproduce the old `_sort_key` exactly.

    `min_distance_km` filters short runs server-side (keeping it consistent with
    server-side pagination rather than filtering a single React page).
    `date_from`/`date_to` (inclusive, R2.7 T4b) are the range the Training-tab
    date picker uses; they compose with, and are a superset of, `year`/`month`.
    """
    # Column-only query, not `db.query(Activity, ShoeRun, OwnedShoe)`: hydrating ~710
    # full ORM entities (incl. the unused `raw_json`/`description` blobs) cost ~63 ms
    # vs ~10.5 ms for just the 16 columns the projection reads (~6x, measured on the
    # live DB). Identical rows/filters/ordering/output — only the loading changed, in
    # keeping with the seam rationale (CLAUDE.md §4.4: swap internals, zero caller
    # changes). Every field is a plain column, so no property logic is duplicated.
    q = (
        db.query(
            Activity.id, Activity.run_date, Activity.distance_km, Activity.source,
            Activity.moving_time_s, Activity.avg_pace_s_per_km, Activity.avg_hr,
            Activity.elevation_gain_m, Activity.name, Activity.elapsed_time_s,
            Activity.activity_tag, Activity.strava_activity_id,
            ShoeRun.id.label("shoe_run_id"),
            OwnedShoe.id.label("s_id"), OwnedShoe.brand.label("s_brand"),
            OwnedShoe.model.label("s_model"), OwnedShoe.nickname.label("s_nickname"),
        )
        .select_from(Activity)
        .outerjoin(ShoeRun, ShoeRun.activity_id == Activity.id)
        .outerjoin(OwnedShoe, OwnedShoe.id == ShoeRun.owned_shoe_id)
        .filter(Activity.activity_type == "Run", Activity.run_date.isnot(None))
    )

    if year is not None:
        q = q.filter(func.strftime("%Y", Activity.run_date) == f"{year:04d}")
    if month is not None:
        q = q.filter(func.strftime("%m", Activity.run_date) == f"{month:02d}")
    if date_from is not None:
        q = q.filter(Activity.run_date >= date_from)
    if date_to is not None:
        q = q.filter(Activity.run_date <= date_to)
    if shoe_id is not None:
        q = q.filter(ShoeRun.owned_shoe_id == shoe_id)
    if min_distance_km is not None:
        q = q.filter(Activity.distance_km >= min_distance_km)

    # Newest first, with the same deterministic tiebreak as the old _sort_key
    # (date, strava_activity_id or 0, shoe_run_id or 0) so pagination is stable.
    q = q.order_by(
        Activity.run_date.desc(),
        func.coalesce(Activity.strava_activity_id, 0).desc(),
        func.coalesce(ShoeRun.id, 0).desc(),
    )

    if offset:
        q = q.offset(offset)
    if limit is not None:
        q = q.limit(limit)

    return [_row_to_unified(row) for row in q.all()]


_UNSET = object()  # "field not supplied" sentinel for the partial update below


def get_activity_detail(db: Session, activity_id: int) -> dict:
    """Full field set for one activity (R2.7 T6 detail view), including the fields
    the list projection omits (description, elevation, cadence, calories, training
    load/focus) and the current shoe attribution. Raises LookupError if missing."""
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if a is None:
        raise LookupError(f"Activity {activity_id} not found")
    attr = db.query(ShoeRun).filter(ShoeRun.activity_id == activity_id).first()
    shoe = db.query(OwnedShoe).filter(OwnedShoe.id == attr.owned_shoe_id).first() if attr else None
    return {
        "id": a.id,
        "source": a.source,
        "name": a.name,
        "description": a.description,
        "run_date": a.run_date.isoformat() if a.run_date else None,
        "distance_km": a.distance_km,
        "moving_time_s": a.moving_time_s,
        "elapsed_time_s": a.elapsed_time_s,
        "avg_pace": rotation.seconds_to_pace(a.avg_pace_s_per_km) if a.avg_pace_s_per_km else None,
        "avg_hr": a.avg_hr,
        "max_hr": a.max_hr,
        "elevation_gain_m": a.elevation_gain_m,
        "avg_cadence": a.avg_cadence,
        "calories": a.calories,
        "training_load": a.training_load,
        "training_focus": a.training_focus,
        "activity_tag": a.activity_tag,
        "strava_activity_id": a.strava_activity_id,
        "shoe": {"id": shoe.id, "brand": shoe.brand, "model": shoe.model, "nickname": shoe.nickname} if shoe else None,
    }


def update_activity(
    db: Session,
    activity_id: int,
    *,
    activity_tag=_UNSET,
    name=_UNSET,
    description=_UNSET,
) -> Activity:
    """Partial-update the editable fields of an activity (R2.7 T6): tag, name,
    description. Only supplied fields change (the `_UNSET` sentinel distinguishes
    "clear to null" from "leave alone"). Tag validity is the caller's contract.
    Raises LookupError if the activity is missing."""
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if a is None:
        raise LookupError(f"Activity {activity_id} not found")
    if activity_tag is not _UNSET:
        a.activity_tag = activity_tag
    if name is not _UNSET:
        a.name = name
    if description is not _UNSET:
        a.description = description
    db.commit()
    db.refresh(a)
    return a
