"""
Longitudinal analytics — shoe performance and wear curves (R5.5.1, R5.5.2).

Job: answer "how does this shoe (or model) run?" and "how fast do my shoes
wear out?" from run history, computed once here and served identically to the
REST endpoints and the MCP tools (CLAUDE.md §2). Read-only: nothing is stored,
no limit is ever changed, no schema is involved.

R5.5.1 — shoe performance. The comparison uses **steady runs only**, through
the form trend's own filter (`training_trends.m_per_beat`: untagged or Easy /
Long Run, ≥ 5 km, avg HR present, no long stops — imported, not copied, so the
two surfaces can never disagree on what "steady" means). Even so, pace by shoe
mostly reflects what the shoe was *used for* (a racer is worn on fast days), so
every payload carries `PERFORMANCE_CAVEAT` and the run counts, and below
`MIN_SHOE_STEADY_RUNS` steady runs the medians are None — the service refuses a
verdict rather than print a number from a handful of runs. Heuristic (B20).

R5.5.2 — wear curves. A per-shoe weekly mileage series (cumulative from the
shoe's starting mileage) and, across *retired* shoes, the mileage at which each
shoe type actually got retired. The type figure yields an advisory
`suggested_limit_km` only; it is never written anywhere — changing a limit
stays the runner's call (CLAUDE.md §2.4).

Scale: `model_performance` / `rotation_insights` make one whole-history pass
over the unioned runs in Python — an O(N) pass, acceptable and labelled at
personal scale (~1k runs), as in strava_stats.personal_bests (CLAUDE.md §12).
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import OwnedShoe
from app.services import activities as activities_svc
# Private by convention, shared on purpose — the same moving-seconds fallback the
# form trend uses (CLAUDE.md §6 trap: renaming it in activities.py breaks this too).
from app.services.activities import UnifiedActivity, _effective_moving_s
from app.services.training_trends import m_per_beat
from app.utils.shoe_types import default_mileage_limit

# --- thresholds (heuristic) -------------------------------------------------
MIN_SHOE_STEADY_RUNS = 10        # fewer steady runs → medians None; exactly 10 is enough
MIN_RETIRED_FOR_SUGGESTION = 3   # retired pairs of a type needed before suggesting a limit; exactly 3 is enough
SUGGESTION_ROUND_KM = 10         # suggested limits are rounded to the nearest 10 km
PERFORMANCE_CAVEAT = (
    "Pace by shoe mostly reflects what the shoe was used for, so only steady runs "
    "are compared and the run counts are shown; treat differences as hints, not a verdict."
)


@dataclass
class ShoePerformance:
    """Steady-run medians for one pair. Medians are None unless `enough_data`."""
    owned_shoe_id: int
    runs: int                              # every attributed run
    km: float                              # total attributed distance, 1 dp
    steady_runs: int                       # runs passing the form-trend steady filter
    median_m_per_beat: Optional[float]     # 3 dp
    median_pace_s_per_km: Optional[int]
    median_avg_hr: Optional[int]
    enough_data: bool
    min_steady_runs: int = MIN_SHOE_STEADY_RUNS
    heuristic: bool = True
    caveat: str = PERFORMANCE_CAVEAT


@dataclass
class ModelPerformance:
    """The same numbers pooled across every pair of one shoe model."""
    brand: str                             # spelling of the lowest-id pair
    model: str
    pair_ids: list[int]                    # sorted
    runs: int
    km: float
    steady_runs: int
    median_m_per_beat: Optional[float]
    median_pace_s_per_km: Optional[int]
    median_avg_hr: Optional[int]
    enough_data: bool
    min_steady_runs: int = MIN_SHOE_STEADY_RUNS
    heuristic: bool = True
    caveat: str = PERFORMANCE_CAVEAT


@dataclass
class WearWeek:
    week: str                              # ISO week label "YYYY-Www"
    km: float
    cumulative_km: float                   # starts from the shoe's starting_mileage


@dataclass
class WearCurve:
    owned_shoe_id: int
    weeks: list[WearWeek]                  # first attributed run's week → last's, empty weeks included
    current_mileage: float
    mileage_limit: Optional[float]
    pct_of_limit: Optional[float]          # current / limit × 100, 1 dp; None without a limit
    status: str


@dataclass
class TypeWear:
    """Where retired shoes of one type actually ended. `suggested_limit_km` is
    advisory only — nothing in the app applies it."""
    shoe_type: str
    retired_count: int
    median_final_km: float                 # 1 dp
    default_limit_km: float
    suggested_limit_km: Optional[float]    # None below MIN_RETIRED_FOR_SUGGESTION


@dataclass
class ShoeInsights:
    performance: ShoePerformance
    model: ModelPerformance
    wear: WearCurve
    type_wear: Optional[TypeWear]


@dataclass
class RotationInsights:
    models: list[ModelPerformance]
    wear_by_type: list[TypeWear]


# --- helpers ----------------------------------------------------------------

def _stats(runs: list[UnifiedActivity]) -> dict:
    """Shared run count / km / steady medians for a list of attributed runs."""
    steady = [r for r in runs if m_per_beat(r) is not None]
    enough = len(steady) >= MIN_SHOE_STEADY_RUNS
    out = {
        "runs": len(runs),
        "km": round(sum(r.distance_km or 0.0 for r in runs), 1),
        "steady_runs": len(steady),
        "median_m_per_beat": None,
        "median_pace_s_per_km": None,
        "median_avg_hr": None,
        "enough_data": enough,
    }
    if enough:
        out["median_m_per_beat"] = round(statistics.median(m_per_beat(r) for r in steady), 3)
        # m_per_beat() passed, so moving seconds and distance are present and > 0.
        out["median_pace_s_per_km"] = round(statistics.median(
            _effective_moving_s(r) / r.distance_km for r in steady))
        out["median_avg_hr"] = round(statistics.median(r.avg_hr for r in steady))
    return out


def _get_shoe(db: Session, owned_shoe_id: int) -> OwnedShoe:
    shoe = db.get(OwnedShoe, owned_shoe_id)
    if shoe is None:
        raise LookupError(f"Owned shoe {owned_shoe_id} not found")
    return shoe


def _model_key(brand: str, model: str) -> tuple[str, str]:
    return ((brand or "").strip().lower(), (model or "").strip().lower())


def _week_label(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# --- R5.5.1 -----------------------------------------------------------------

def shoe_performance(db: Session, owned_shoe_id: int) -> ShoePerformance:
    """Steady-run performance of one pair.

    Raises:
        LookupError: no such owned shoe.
    """
    _get_shoe(db, owned_shoe_id)
    runs = activities_svc.unified_activities(db, shoe_id=owned_shoe_id)
    return ShoePerformance(owned_shoe_id=owned_shoe_id, **_stats(runs))


def model_performance(db: Session) -> list[ModelPerformance]:
    """Steady-run performance per shoe model, pooled over its pairs.

    Group key is (brand, model) stripped and lower-cased, so "Nike"/"nike " merge;
    the output spelling comes from the lowest-id pair. Models with no pairs don't
    appear; sorted by run count, most-run first. One whole-history in-Python
    pass (O(N), labelled — see the module docstring)."""
    shoes = db.query(OwnedShoe).order_by(OwnedShoe.id.asc()).all()
    key_of = {s.id: _model_key(s.brand, s.model) for s in shoes}
    groups: dict[tuple[str, str], list[OwnedShoe]] = defaultdict(list)
    for s in shoes:
        groups[key_of[s.id]].append(s)

    runs_by_key: dict[tuple[str, str], list[UnifiedActivity]] = defaultdict(list)
    for r in activities_svc.unified_activities(db):
        if r.shoe is not None and r.shoe.id in key_of:
            runs_by_key[key_of[r.shoe.id]].append(r)

    out = [
        ModelPerformance(
            brand=pairs[0].brand,
            model=pairs[0].model,
            pair_ids=sorted(p.id for p in pairs),
            **_stats(runs_by_key.get(key, [])),
        )
        for key, pairs in groups.items()
    ]
    out.sort(key=lambda m: (-m.runs, m.pair_ids[0]))
    return out


# --- R5.5.2 -----------------------------------------------------------------

def wear_curve(db: Session, owned_shoe_id: int) -> WearCurve:
    """Weekly mileage and cumulative wear of one pair.

    `weeks` spans the ISO week of the first attributed run to that of the last,
    with empty weeks as km 0; it is empty for a shoe with no runs. Cumulative
    starts from `starting_mileage`.

    Raises:
        LookupError: no such owned shoe.
    """
    shoe = _get_shoe(db, owned_shoe_id)
    runs = activities_svc.unified_activities(db, shoe_id=owned_shoe_id)
    weeks: list[WearWeek] = []
    if runs:
        per_week: dict[str, float] = defaultdict(float)
        for r in runs:
            per_week[_week_label(r.date)] += r.distance_km or 0.0
        first = min(r.date for r in runs)
        last = max(r.date for r in runs)
        monday = first - timedelta(days=first.weekday())
        cumulative = shoe.starting_mileage or 0.0
        while monday <= last:
            label = _week_label(monday)
            km = per_week.get(label, 0.0)
            cumulative += km
            weeks.append(WearWeek(week=label, km=round(km, 1), cumulative_km=round(cumulative, 1)))
            monday += timedelta(weeks=1)
    current = shoe.current_mileage or 0.0
    limit = shoe.mileage_limit
    return WearCurve(
        owned_shoe_id=owned_shoe_id,
        weeks=weeks,
        current_mileage=round(current, 1),
        mileage_limit=limit,
        pct_of_limit=round(current / limit * 100, 1) if limit else None,
        status=shoe.status,
    )


def wear_by_type(db: Session) -> list[TypeWear]:
    """Final mileage of retired shoes, per shoe type (retired shoes with a type
    only; active / for-sale pairs are ignored). `suggested_limit_km` is the
    median rounded to the nearest 10 km once ≥ 3 pairs of the type are retired,
    else None — advisory only, never written anywhere."""
    by_type: dict[str, list[float]] = defaultdict(list)
    for s in db.query(OwnedShoe).filter(
        OwnedShoe.status == "retired", OwnedShoe.shoe_type.isnot(None)
    ).all():
        by_type[s.shoe_type].append(s.current_mileage or 0.0)
    out = []
    for shoe_type, finals in sorted(by_type.items()):
        median = statistics.median(finals)
        suggested = None
        if len(finals) >= MIN_RETIRED_FOR_SUGGESTION:
            suggested = float(round(median / SUGGESTION_ROUND_KM) * SUGGESTION_ROUND_KM)
        out.append(TypeWear(
            shoe_type=shoe_type,
            retired_count=len(finals),
            median_final_km=round(median, 1),
            default_limit_km=default_mileage_limit(shoe_type),
            suggested_limit_km=suggested,
        ))
    return out


# --- composed views ----------------------------------------------------------

def shoe_insights(db: Session, owned_shoe_id: int) -> ShoeInsights:
    """Everything the shoe page / assistant needs about one pair.

    Raises:
        LookupError: no such owned shoe.
    """
    shoe = _get_shoe(db, owned_shoe_id)
    model = next(m for m in model_performance(db)
                 if owned_shoe_id in m.pair_ids)
    type_wear = next((t for t in wear_by_type(db) if t.shoe_type == shoe.shoe_type), None)
    return ShoeInsights(
        performance=shoe_performance(db, owned_shoe_id),
        model=model,
        wear=wear_curve(db, owned_shoe_id),
        type_wear=type_wear,
    )


def rotation_insights(db: Session) -> RotationInsights:
    """Model comparison and retired-shoe wear by type, for the whole rotation."""
    return RotationInsights(models=model_performance(db), wear_by_type=wear_by_type(db))
