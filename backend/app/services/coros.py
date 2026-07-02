"""
Business logic for COROS GPS watch synchronisation.

Wraps coros_client HTTP calls and delegates run persistence to rotation.log_run
so checkpoint detection works on the COROS path too (previously missing from the
REST confirm endpoint).
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import requests
from sqlalchemy.orm import Session

from app.coros_client import activity_to_run_dict, fetch_running_activities, get_coros_config
from app.models.models import ShoeRun
from app.services import rotation, settings as settings_svc


@dataclass
class CorosFetchResult:
    runs: list          # list of activity_to_run_dict dicts
    already_synced: int
    coros_configured: bool


def is_already_logged(db: Session, activity_id: str, act_date: str, dist_km: float) -> bool:
    """
    Two-tier dedup:
    1. Exact coros_activity_id match (primary — used after first sync).
    2. Same date + distance within 0.1km (secondary — catches runs logged
       manually before this feature existed).
    """
    if activity_id and db.query(ShoeRun).filter(
        ShoeRun.coros_activity_id == activity_id
    ).count():
        return True
    return db.query(ShoeRun).filter(
        ShoeRun.run_date == act_date,
        ShoeRun.distance_km.between(dist_km - 0.1, dist_km + 0.1),
    ).count() > 0


def fetch_unsynced(db: Session, days_back: int = 30) -> CorosFetchResult:
    """
    Fetch recent running activities from COROS and return those not yet logged.

    Propagates requests.RequestException and ValueError to the caller — adapters
    map these to HTTP 502 or success:False as appropriate.
    Returns a result with coros_configured=False (not an error) when credentials
    are absent.
    """
    config = get_coros_config()
    if not config:
        return CorosFetchResult(runs=[], already_synced=0, coros_configured=False)

    activities = fetch_running_activities(config, days_back)

    new_runs = []
    already_synced = 0
    for act in activities:
        run = activity_to_run_dict(act)
        if is_already_logged(db, run["coros_activity_id"], run["date"], run["distance_km"]):
            already_synced += 1
        else:
            new_runs.append(run)

    new_runs.sort(key=lambda r: r["date"], reverse=True)
    return CorosFetchResult(runs=new_runs, already_synced=already_synced, coros_configured=True)


def confirm_run(
    db: Session,
    *,
    coros_activity_id: str,
    owned_shoe_id: int,
    run_date: date,
    distance_km: float,
    avg_pace: Optional[str] = None,
    avg_hr: Optional[int] = None,
    notes: Optional[str] = None,
) -> Optional[rotation.RunLogResult]:
    """
    Log a single confirmed COROS run to an owned shoe.

    Idempotent: returns None if the activity_id is already logged.
    Delegates to rotation.log_run(source='coros') so checkpoint detection
    fires on the COROS path (previously it didn't on the REST confirm path).
    Stamps last_coros_sync_at after a successful write.

    Raises LookupError if the shoe doesn't exist (caller decides whether to
    skip or surface the error).
    """
    if coros_activity_id and db.query(ShoeRun).filter(
        ShoeRun.coros_activity_id == coros_activity_id
    ).count():
        return None

    result = rotation.log_run(
        db,
        owned_shoe_id,
        distance_km=distance_km,
        run_date=run_date,
        source="coros",
        coros_activity_id=coros_activity_id,
        avg_pace=avg_pace,
        avg_hr=avg_hr,
        notes=notes,
    )

    settings_svc.set_setting(db, "last_coros_sync_at", datetime.now(timezone.utc).isoformat())
    db.commit()

    return result
