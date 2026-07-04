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


def _build(db: Session) -> list[UnifiedActivity]:
    """The raw run feed, unsorted/unfiltered. Split out so stats helpers can
    reuse it without re-implementing the join.

    One pass over `activities` (runs only), each LEFT-joined to its optional
    `shoe_runs` attribution for shoe info. No dedup — a physical run is a single
    Activity row by construction."""
    shoes = {s.id: s for s in db.query(OwnedShoe).all()}
    attr_by_activity: dict[int, ShoeRun] = {
        sr.activity_id: sr for sr in db.query(ShoeRun).all()
    }

    def _shoe_of(attr: Optional[ShoeRun]) -> Optional[UnifiedShoe]:
        if attr is None:
            return None
        s = shoes.get(attr.owned_shoe_id)
        if s is None:
            return None
        return UnifiedShoe(id=s.id, brand=s.brand, model=s.model, nickname=s.nickname)

    out: list[UnifiedActivity] = []
    for a in db.query(Activity).filter(Activity.activity_type == "Run").all():
        if a.run_date is None:
            continue
        attr = attr_by_activity.get(a.id)
        pace_s = a.avg_pace_s_per_km
        out.append(UnifiedActivity(
            date=a.run_date,
            distance_km=a.distance_km or 0.0,
            source=a.source,
            moving_time_s=a.moving_time_s,
            avg_pace=rotation.seconds_to_pace(pace_s) if pace_s else None,
            avg_pace_s_per_km=pace_s,
            avg_hr=a.avg_hr,
            elevation_m=a.elevation_gain_m,
            name=a.name,
            shoe=_shoe_of(attr),
            strava_activity_id=a.strava_activity_id,
            shoe_run_id=attr.id if attr else None,
        ))

    return out


def unified_activities(
    db: Session,
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    shoe_id: Optional[int] = None,
    min_distance_km: Optional[float] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[UnifiedActivity]:
    """
    The unioned run feed, newest first, with optional filters and stable
    limit/offset pagination.

    `min_distance_km` is an extension over the §3 signature so the Training
    activities list can filter short runs server-side (keeping it consistent
    with server-side pagination rather than filtering a single page in React).
    """
    items = _build(db)

    if year is not None:
        items = [a for a in items if a.date.year == year]
    if month is not None:
        items = [a for a in items if a.date.month == month]
    if shoe_id is not None:
        items = [a for a in items if a.shoe is not None and a.shoe.id == shoe_id]
    if min_distance_km is not None:
        items = [a for a in items if a.distance_km >= min_distance_km]

    items.sort(key=lambda a: a._sort_key, reverse=True)

    if offset:
        items = items[offset:]
    if limit is not None:
        items = items[:limit]
    return items
