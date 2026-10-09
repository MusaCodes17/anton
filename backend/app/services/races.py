"""
Planned races (P3.4) — derived-field helpers shared by the REST router and
the MCP tool, so both report the identical countdown/pace.

Derived fields (days/weeks remaining, target pace) are computed here at the
boundary and never stored: race_date - today is only meaningful "now".
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Activity, PendingCorosRun, PlannedRace, ShoeRun
from app.services import rotation
from app.utils.activity_tags import RACE_RESULT_TAGS

logger = logging.getLogger(__name__)

# A planned race this many days past with nothing run that day is treated as
# not run and removed. 3 = the COROS poller's default lookback
# (COROS_POLL_LOOKBACK_DAYS), so a watch that syncs late has had its run queued
# before we conclude there's nothing to sync. It also leaves a few days to mark
# a race done by hand.
UNRUN_RACE_GRACE_DAYS = 3


def _activity_result_s(a: Activity) -> Optional[int]:
    """A race result from a run, on the records clock (R8.1): elapsed (gun) time,
    else moving time, else pace × distance so the result is set."""
    return a.elapsed_time_s or a.moving_time_s or (
        round(a.avg_pace_s_per_km * a.distance_km) if a.avg_pace_s_per_km and a.distance_km else None
    )


def create_completed_from_activity(db: Session, activity_id: int) -> PlannedRace:
    """Promote an activity to a *completed* race row (R2.7 T6) — the workflow for
    "I ran a race and want it in the races dashboard". Pre-fills date, distance,
    and the activity's time as the result, and back-links the race to the
    activity (T7) so the past-race row deep-links to its full stats. Raises
    LookupError if the activity is missing, ValueError if it has no distance to
    race over. Owns the commit.
    """
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if a is None:
        raise LookupError(f"Activity {activity_id} not found")
    if not a.distance_km:
        raise ValueError("Activity has no distance to promote to a race")

    result_s = _activity_result_s(a)
    name = a.name or (f"Race {a.run_date.isoformat()}" if a.run_date else "Race")
    attr = db.query(ShoeRun).filter(ShoeRun.activity_id == activity_id).first()

    race = PlannedRace(
        name=name,
        race_date=a.run_date,
        distance_km=a.distance_km,
        status="completed",
        result_time_s=result_s,
        planned_shoe_id=attr.owned_shoe_id if attr else None,
        activity_id=activity_id,   # T7: back-link the race to the run it was
    )
    db.add(race)
    db.commit()
    db.refresh(race)
    return race


def link_activity(db: Session, race_id: int, activity_id: int) -> PlannedRace:
    """Resolve a race as run by linking it to the activity that was the race
    (R8.3) — e.g. a planned race the prune kept because a run exists that day.
    Marks it completed, takes the result from the run, and back-links it (T7)
    so the past-race row deep-links to the run. The run itself is untouched.

    Raises LookupError if the race or activity is missing; ValueError if the
    activity is already another race's result (one run can't be two races).
    Owns the commit.
    """
    race = db.query(PlannedRace).filter(PlannedRace.id == race_id).first()
    if race is None:
        raise LookupError(f"Race {race_id} not found")
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if a is None:
        raise LookupError(f"Activity {activity_id} not found")
    other = (
        db.query(PlannedRace)
        .filter(PlannedRace.activity_id == activity_id, PlannedRace.id != race_id)
        .first()
    )
    if other is not None:
        raise ValueError(f"That run is already the result of {other.name!r}")

    race.activity_id = activity_id
    race.status = "completed"
    race.result_time_s = _activity_result_s(a)
    db.commit()
    db.refresh(race)
    return race


def _target_pace(race: PlannedRace) -> Optional[str]:
    if race.target_time_s and race.distance_km:
        return rotation.seconds_to_pace(race.target_time_s / race.distance_km)
    return None


def attach_derived(race: PlannedRace, today: Optional[date] = None) -> PlannedRace:
    """Attach days_remaining / weeks_remaining / target_pace so the Pydantic
    response (from_attributes) can read them. weeks_remaining is days // 7
    (race today → 0 days, 0 weeks; past races go negative)."""
    today = today or date.today()
    days = (race.race_date - today).days
    race.days_remaining = days
    race.weeks_remaining = days // 7
    race.target_pace = _target_pace(race)
    race.from_activity = False  # PlannedRace rows are never activity-synthesized
    return race


def race_to_dict(race: PlannedRace, today: Optional[date] = None) -> dict:
    """Flat dict for MCP — same computed shape as the API response."""
    attach_derived(race, today)
    shoe = race.planned_shoe
    return {
        "id": race.id,
        "name": race.name,
        "race_date": race.race_date.isoformat() if race.race_date else None,
        "distance_km": race.distance_km,
        "target_time_s": race.target_time_s,
        "target_pace": race.target_pace,
        "location": race.location,
        "status": race.status,
        "result_time_s": race.result_time_s,
        "activity_id": race.activity_id,
        "days_remaining": race.days_remaining,
        "weeks_remaining": race.weeks_remaining,
        "planned_shoe": (
            {"id": shoe.id, "brand": shoe.brand, "model": shoe.model, "nickname": shoe.nickname}
            if shoe else None
        ),
        "notes": race.notes,
    }


def prune_unrun_races(db: Session, today: Optional[date] = None) -> list[str]:
    """Delete planned races that evidently didn't happen, so a dropped race
    (e.g. a parkrun you skipped) stops sitting in "Past races" as un-done.

    A race is pruned only when ALL hold — positive evidence, not absence of a
    status update (CLAUDE.md §7 interlock):
      - status is still 'planned' (completed and deliberately 'skipped' rows
        are the runner's record and are kept) and it has no linked activity;
      - race_date is at least UNRUN_RACE_GRACE_DAYS before today;
      - no Activity exists on race_date (any source, any distance);
      - no unresolved COROS run is waiting in the inbox for race_date — that
        run may be the race, and confirming it should be possible.

    Deals-domain-style disposal is acceptable here because the row records an
    intention, not a run (history-is-sacred covers runs, not plans). Returns
    the deleted race names. Owns the commit (only when something was deleted).
    """
    today = today or date.today()
    cutoff = today - timedelta(days=UNRUN_RACE_GRACE_DAYS)
    candidates = (
        db.query(PlannedRace)
        .filter(
            PlannedRace.status == "planned",
            PlannedRace.activity_id.is_(None),
            PlannedRace.race_date <= cutoff,
        )
        .all()
    )
    pruned = []
    for race in candidates:
        ran = db.query(Activity.id).filter(Activity.run_date == race.race_date).first()
        waiting = (
            db.query(PendingCorosRun.id)
            .filter(PendingCorosRun.run_date == race.race_date, PendingCorosRun.status == "pending")
            .first()
        )
        if ran or waiting:
            continue
        logger.info("Pruning unrun race %r (%s): no run logged or waiting to sync", race.name, race.race_date)
        pruned.append(race.name)
        db.delete(race)
    if pruned:
        db.commit()
    return pruned


def list_races(db: Session, today: Optional[date] = None) -> list:
    """All races, soonest first, with derived fields attached.

    Planned races that were never run are pruned first (prune_unrun_races).

    Includes synthetic entries for activities tagged 'Race' or 'Parkrun' whose
    run_date is in the past and that aren't already back-linked to a PlannedRace
    row (to avoid duplicates). Synthetic items carry from_activity=True so the
    frontend knows they cannot be edited/deleted/marked-done via the races API.
    """
    today = today or date.today()

    # Read-time housekeeping: every races surface (REST, MCP, weekly summary,
    # race advisor) passes through here, so this is the one place that sees a
    # stale plan regardless of whether COROS is connected.
    prune_unrun_races(db, today)

    races = db.query(PlannedRace).order_by(PlannedRace.race_date.asc()).all()
    for r in races:
        attach_derived(r, today)

    # Activity-tagged past races not already referenced by any PlannedRace row.
    linked_ids = {r.activity_id for r in races if r.activity_id is not None}
    q = (
        db.query(Activity)
        .filter(
            Activity.activity_tag.in_(tuple(RACE_RESULT_TAGS)),
            Activity.run_date < today,
        )
    )
    if linked_ids:
        q = q.filter(Activity.id.notin_(linked_ids))
    tagged = q.order_by(Activity.run_date.desc()).all()

    synthetic = []
    for a in tagged:
        days = (a.run_date - today).days
        synthetic.append(SimpleNamespace(
            id=-(a.id),   # negative: never collides with a real PlannedRace.id
            name=a.name or f"Race {a.run_date.isoformat()}",
            race_date=a.run_date,
            distance_km=a.distance_km,
            target_time_s=None,
            location=None,
            planned_shoe_id=None,
            notes=None,
            status="completed",
            result_time_s=_activity_result_s(a),
            activity_id=a.id,
            created_at=datetime.combine(a.run_date, datetime.min.time()),
            planned_shoe=None,
            days_remaining=days,
            weeks_remaining=days // 7,
            target_pace=None,
            from_activity=True,
        ))

    return races + synthetic
