"""
The shared COROS confirm path (R5.7).

Every way a COROS run gets logged — the app's "New runs" inbox, the
`confirm_coros_run` MCP tool — goes through `confirm_run` here, which delegates
to `rotation.log_run` (the single run writer) and resolves the matching
`pending_coros_runs` row. Also owns the two-tier "already logged?" dedup the
poller uses. (The legacy Open-API fetch that used to live here was removed with
`coros_client.py` — see design_decisions C11.)
"""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Activity, PendingCorosRun
from app.services import rotation, settings as settings_svc


def is_already_logged(db: Session, activity_id: str, act_date: str, dist_km: float) -> bool:
    """
    Two-tier dedup:
    1. Exact coros_activity_id match (primary — used after first sync).
    2. Same date + distance within 0.1km (secondary — catches runs logged
       manually before this feature existed).
    """
    if activity_id and db.query(Activity).filter(
        Activity.coros_activity_id == activity_id
    ).count():
        return True
    return db.query(Activity).filter(
        Activity.run_date == date.fromisoformat(act_date),
        Activity.distance_km.between(dist_km - 0.1, dist_km + 0.1),
    ).count() > 0


def resolve_pending(db: Session, label_id: str) -> None:
    """Mark the pending-inbox row for this COROS label confirmed (R5.7 §7). Does NOT
    commit. Called from confirm_run so the app inbox, the REST confirm and the
    `confirm_coros_run` MCP tool all clear the same queue: confirming via Claude
    removes the run from the app, and vice versa. A dismissed row is also marked
    confirmed — the run *is* logged now, which is the truth the queue must show."""
    if not label_id:
        return
    row = db.query(PendingCorosRun).filter(
        PendingCorosRun.label_id == label_id,
        PendingCorosRun.status.in_(("pending", "dismissed")),
    ).first()
    if row is not None:
        row.status = "confirmed"
        row.resolved_at = datetime.now(timezone.utc)


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
    name: Optional[str] = None,
    elevation_gain_m: Optional[float] = None,
    moving_time_s: Optional[int] = None,
    elapsed_time_s: Optional[int] = None,
    avg_cadence: Optional[float] = None,
    calories: Optional[float] = None,
    training_load: Optional[float] = None,
    training_focus: Optional[str] = None,
    activity_tag: Optional[str] = None,
) -> Optional[rotation.RunLogResult]:
    """
    Log a single confirmed COROS run to an owned shoe.

    Idempotent: returns None if the activity_id is already logged. Either way the
    matching pending-inbox row (if any) is resolved to `confirmed` (R5.7 §7).
    Delegates to rotation.log_run(source='coros') so checkpoint detection
    fires on the COROS path (previously it didn't on the REST confirm path).
    Stamps last_coros_sync_at after a successful write.

    The `name`..`activity_tag` fields (R2.7 T2) are the richer per-run data the
    COROS sync now captures instead of discarding; all optional/nullable and
    passed straight through to the canonical Activity. `activity_tag` must be a
    member of the ACTIVITY_TAGS vocabulary — the caller (the confirmation-gated
    MCP prompt) is responsible for confirming a suggested tag with the runner
    before it reaches here (C9); this function does not infer.

    Raises LookupError if the shoe doesn't exist (caller decides whether to
    skip or surface the error).
    """
    if coros_activity_id and db.query(Activity).filter(
        Activity.coros_activity_id == coros_activity_id
    ).count():
        # Already logged by some path: still make sure the inbox row isn't left
        # dangling as "pending" (e.g. logged via Claude before the poller saw it).
        resolve_pending(db, coros_activity_id)
        db.commit()
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
        name=name,
        elevation_gain_m=elevation_gain_m,
        moving_time_s=moving_time_s,
        elapsed_time_s=elapsed_time_s,
        avg_cadence=avg_cadence,
        calories=calories,
        training_load=training_load,
        training_focus=training_focus,
        activity_tag=activity_tag,
    )

    settings_svc.set_setting(db, "last_coros_sync_at", datetime.now(timezone.utc).isoformat())
    resolve_pending(db, coros_activity_id)
    db.commit()

    return result
