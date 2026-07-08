"""
Planned races (P3.4) — derived-field helpers shared by the REST router and
the MCP tool, so both report the identical countdown/pace.

Derived fields (days/weeks remaining, target pace) are computed here at the
boundary and never stored: race_date - today is only meaningful "now".
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Activity, PlannedRace, ShoeRun
from app.services import rotation


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

    # Prefer real moving time; fall back to pace × distance so the result is set.
    result_s = a.moving_time_s or (
        round(a.avg_pace_s_per_km * a.distance_km) if a.avg_pace_s_per_km else None
    )
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


def list_races(db: Session, today: Optional[date] = None) -> list[PlannedRace]:
    """All races, soonest first, with derived fields attached."""
    races = db.query(PlannedRace).order_by(PlannedRace.race_date.asc()).all()
    for r in races:
        attach_derived(r, today)
    return races
