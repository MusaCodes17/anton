"""
Strava dedup + backfill (§4) and mileage reconciliation (§5).

Core invariant: every physical run exists at most once in shoe_runs,
regardless of how many systems recorded it. Two passes:

  1. MATCH (link, don't create): a Strava run that lines up with an existing
     shoe_run (same local date, distance within tolerance) is *linked* — we
     stamp shoe_runs.strava_activity_id, never create a duplicate. The
     human-confirmed COROS/manual shoe assignment wins over the Strava gear
     column; shoe conflicts are logged, not silently resolved.
  2. BACKFILL (create): a Strava run with no existing counterpart, whose gear
     maps to an owned shoe, becomes a new shoe_run (source='strava').

Everything is computed first as a plan (no writes). execute_backfill applies
it in a single transaction. The CLI defaults to dry-run.

Mileage (§5): owned_shoes.current_mileage is a STORED counter
(starting_mileage + sum(runs)). Backfilling real runs for history that was
already baked into a shoe's starting_mileage would double-count. The
'preserve' policy (default) reduces starting_mileage by the backfilled km
(floored at 0) so a shoe's displayed total stays put while gaining real run
rows. Shoes whose starting offset overlaps the backfill are FLAGGED — the
plan forbids auto-resolving those without a human decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import OwnedShoe, ShoeRun, StravaActivity, StravaGearMapping
from app.services import rotation

DISTANCE_TOLERANCE_KM = 0.1  # identical to the COROS sync protocol
OFFSET_EPSILON_KM = 1.0       # ignore rounding dust when deciding "offset overlaps"

# Mileage policies for the commit step.
POLICY_PRESERVE = "preserve"      # reduce starting_mileage by backfill km (keep total)
POLICY_ADD = "add"                # naively add backfill km (double-counts pre-tracker offsets)
POLICY_OFFSET_ZERO = "offset-zero"  # zero starting_mileage, let runs define the total
MILEAGE_POLICIES = (POLICY_PRESERVE, POLICY_ADD, POLICY_OFFSET_ZERO)


@dataclass
class LinkIntent:
    strava_activity_id: int
    shoe_run_id: int
    run_shoe_id: int
    gear_shoe_id: Optional[int]  # what the Strava gear maps to
    conflict: bool               # gear_shoe_id set and != run_shoe_id
    kind: str                    # 'exact' | 'date-shift'
    detail: str


@dataclass
class CreateIntent:
    strava_activity_id: int
    owned_shoe_id: int
    run_date: object
    distance_km: float
    avg_pace: Optional[str]
    avg_hr: Optional[int]


@dataclass
class ShoeReconcile:
    shoe_id: int
    name: str
    current_mileage: float
    sum_existing_runs: float
    implied_offset: float
    sum_backfill_km: float
    proposed_final: float
    flagged: bool


@dataclass
class BackfillReport:
    matched: list[LinkIntent] = field(default_factory=list)
    date_shift: list[LinkIntent] = field(default_factory=list)
    ambiguous: list[dict] = field(default_factory=list)
    to_create: list[CreateIntent] = field(default_factory=list)
    skipped_unmapped: list[int] = field(default_factory=list)   # strava_activity_id, gear present but no shoe
    skipped_no_gear: list[int] = field(default_factory=list)    # strava_activity_id, no gear at all
    reconcile: list[ShoeReconcile] = field(default_factory=list)
    committed: bool = False

    @property
    def conflicts(self) -> list[LinkIntent]:
        return [m for m in self.matched if m.conflict]


def _shoe_name(shoe: OwnedShoe) -> str:
    return f"{shoe.brand} {shoe.model}" + (f" ({shoe.nickname})" if shoe.nickname else "")


def _linked_strava_ids(db: Session) -> set[int]:
    rows = db.query(ShoeRun.strava_activity_id).filter(ShoeRun.strava_activity_id.isnot(None)).all()
    return {r[0] for r in rows}


def plan_backfill(
    db: Session,
    *,
    distance_tol: float = DISTANCE_TOLERANCE_KM,
    mileage_policy: str = POLICY_PRESERVE,
) -> BackfillReport:
    """
    Analyze without writing. Returns the full match/backfill/reconcile plan.
    """
    report = BackfillReport()

    gear_map = {m.gear_name: m.owned_shoe_id for m in db.query(StravaGearMapping).all()}
    already_linked = _linked_strava_ids(db)

    strava_runs = (
        db.query(StravaActivity)
        .filter(StravaActivity.activity_type == "Run")
        .order_by(StravaActivity.run_date)
        .all()
    )

    # shoe_runs already claimed by a link this pass (so two Strava runs can't
    # both grab the same existing run).
    claimed_run_ids: set[int] = set()

    for s in strava_runs:
        if s.strava_activity_id in already_linked:
            continue
        if s.run_date is None or s.distance_km is None:
            # No date/distance to match on — treat as backfill candidate below.
            pass

        gear_shoe_id = gear_map.get(s.gear_name) if s.gear_name else None

        # --- exact-day candidates ---
        exact = []
        if s.run_date is not None and s.distance_km is not None:
            exact = (
                db.query(ShoeRun)
                .filter(
                    ShoeRun.strava_activity_id.is_(None),
                    ShoeRun.run_date == s.run_date,
                    ShoeRun.distance_km.between(
                        s.distance_km - distance_tol, s.distance_km + distance_tol
                    ),
                )
                .all()
            )
            exact = [r for r in exact if r.id not in claimed_run_ids]

        if len(exact) == 1:
            run = exact[0]
            claimed_run_ids.add(run.id)
            report.matched.append(_make_link(s, run, gear_shoe_id, "exact"))
            continue
        if len(exact) > 1:
            # tie-break on closest distance
            exact.sort(key=lambda r: abs(r.distance_km - s.distance_km))
            best, second = exact[0], exact[1]
            if abs(best.distance_km - s.distance_km) < abs(second.distance_km - s.distance_km):
                claimed_run_ids.add(best.id)
                report.matched.append(_make_link(s, best, gear_shoe_id, "exact"))
            else:
                report.ambiguous.append({
                    "strava_activity_id": s.strava_activity_id,
                    "run_date": str(s.run_date),
                    "distance_km": s.distance_km,
                    "candidate_run_ids": [r.id for r in exact],
                })
            continue

        # --- widen ±1 day (date-shift): flag for manual review, never auto-link ---
        shift = []
        if s.run_date is not None and s.distance_km is not None:
            lo, hi = s.run_date - timedelta(days=1), s.run_date + timedelta(days=1)
            shift = (
                db.query(ShoeRun)
                .filter(
                    ShoeRun.strava_activity_id.is_(None),
                    ShoeRun.run_date.between(lo, hi),
                    ShoeRun.distance_km.between(
                        s.distance_km - distance_tol, s.distance_km + distance_tol
                    ),
                )
                .all()
            )
            shift = [r for r in shift if r.id not in claimed_run_ids]

        if shift:
            report.date_shift.append(_make_link(s, shift[0], gear_shoe_id, "date-shift"))
            continue

        # --- backfill candidate (no existing counterpart) ---
        if gear_shoe_id is not None:
            report.to_create.append(CreateIntent(
                strava_activity_id=s.strava_activity_id,
                owned_shoe_id=gear_shoe_id,
                run_date=s.run_date,
                distance_km=s.distance_km,
                avg_pace=rotation.seconds_to_pace(s.avg_pace_s_per_km) if s.avg_pace_s_per_km else None,
                avg_hr=s.avg_hr,
            ))
        elif s.gear_name:
            report.skipped_unmapped.append(s.strava_activity_id)
        else:
            report.skipped_no_gear.append(s.strava_activity_id)

    report.reconcile = _reconcile(db, report, mileage_policy)
    return report


def _make_link(s: StravaActivity, run: ShoeRun, gear_shoe_id: Optional[int], kind: str) -> LinkIntent:
    conflict = gear_shoe_id is not None and gear_shoe_id != run.owned_shoe_id
    detail = (
        f"strava {s.strava_activity_id} ({s.run_date}, {s.distance_km}km) "
        f"↔ run #{run.id} on shoe {run.owned_shoe_id}"
    )
    if conflict:
        detail += f" [gear maps to shoe {gear_shoe_id}]"
    return LinkIntent(
        strava_activity_id=s.strava_activity_id,
        shoe_run_id=run.id,
        run_shoe_id=run.owned_shoe_id,
        gear_shoe_id=gear_shoe_id,
        conflict=conflict,
        kind=kind,
        detail=detail,
    )


def _reconcile(db: Session, report: BackfillReport, policy: str) -> list[ShoeReconcile]:
    """Per-shoe mileage table for the shoes that will receive backfill runs."""
    by_shoe: dict[int, float] = {}
    for c in report.to_create:
        by_shoe[c.owned_shoe_id] = by_shoe.get(c.owned_shoe_id, 0.0) + (c.distance_km or 0.0)

    out: list[ShoeReconcile] = []
    for shoe_id, sum_backfill in sorted(by_shoe.items()):
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            continue
        sum_existing = (
            db.query(func.coalesce(func.sum(ShoeRun.distance_km), 0.0))
            .filter(ShoeRun.owned_shoe_id == shoe_id)
            .scalar()
        ) or 0.0
        implied_offset = shoe.current_mileage - sum_existing
        proposed_final = _proposed_final(shoe.current_mileage, implied_offset, sum_backfill, policy)
        flagged = implied_offset > OFFSET_EPSILON_KM and sum_backfill > 0
        out.append(ShoeReconcile(
            shoe_id=shoe_id,
            name=_shoe_name(shoe),
            current_mileage=round(shoe.current_mileage, 2),
            sum_existing_runs=round(sum_existing, 2),
            implied_offset=round(implied_offset, 2),
            sum_backfill_km=round(sum_backfill, 2),
            proposed_final=round(proposed_final, 2),
            flagged=flagged,
        ))
    return out


def _proposed_final(current: float, implied_offset: float, sum_backfill: float, policy: str) -> float:
    if policy == POLICY_ADD:
        return current + sum_backfill
    if policy == POLICY_OFFSET_ZERO:
        # drop the offset entirely; total becomes existing runs + backfill
        existing_runs = current - implied_offset
        return existing_runs + sum_backfill
    # preserve: new_starting = max(0, old_starting - sum_backfill)
    new_offset = max(0.0, implied_offset - sum_backfill)
    existing_runs = current - implied_offset
    return new_offset + existing_runs + sum_backfill


def execute_backfill(db: Session, *, mileage_policy: str = POLICY_PRESERVE) -> BackfillReport:
    """
    Re-plan and apply in ONE transaction: link matched runs, create backfill
    runs (source='strava'), and adjust each affected shoe's mileage per the
    chosen policy. Idempotent — a second run finds everything already linked
    and creates nothing.
    """
    if mileage_policy not in MILEAGE_POLICIES:
        raise ValueError(f"unknown mileage_policy {mileage_policy!r}; expected one of {MILEAGE_POLICIES}")

    report = plan_backfill(db, mileage_policy=mileage_policy)

    # 1. Link matched (exact) runs — never date-shift (manual only).
    for link in report.matched:
        run = db.query(ShoeRun).filter(ShoeRun.id == link.shoe_run_id).first()
        if run and run.strava_activity_id is None:
            run.strava_activity_id = link.strava_activity_id

    # 2. Create backfill runs via rotation.log_run — the single sanctioned
    #    ShoeRun write path. increment_mileage=False lets us apply the mileage
    #    policy explicitly below; commit=False batches every write into this
    #    function's single transaction.
    created_km_by_shoe: dict[int, float] = {}
    for c in report.to_create:
        rotation.log_run(
            db,
            c.owned_shoe_id,
            distance_km=c.distance_km,
            run_date=c.run_date,
            source="strava",
            strava_activity_id=c.strava_activity_id,
            avg_pace=c.avg_pace,
            avg_hr=c.avg_hr,
            increment_mileage=False,
            commit=False,
        )
        created_km_by_shoe[c.owned_shoe_id] = created_km_by_shoe.get(c.owned_shoe_id, 0.0) + (c.distance_km or 0.0)

    # 3. Apply mileage policy per affected shoe.
    for shoe_id, added_km in created_km_by_shoe.items():
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            continue
        if mileage_policy == POLICY_ADD:
            shoe.current_mileage += added_km
        elif mileage_policy == POLICY_OFFSET_ZERO:
            shoe.current_mileage = max(0.0, shoe.current_mileage - shoe.starting_mileage) + added_km
            shoe.starting_mileage = 0.0
        else:  # preserve
            reduce_by = min(shoe.starting_mileage, added_km)
            shoe.starting_mileage -= reduce_by
            shoe.current_mileage += (added_km - reduce_by)

    db.commit()
    report.committed = True
    return report
