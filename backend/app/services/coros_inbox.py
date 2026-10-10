"""
COROS "New runs" inbox — list / confirm / dismiss pending runs (R5.7 §6).

The runner's decision point for runs the poller queued. Confirming goes through
`coros.confirm_run` — the SAME function behind the `confirm_coros_run` MCP tool
and the REST confirm — which delegates to `rotation.log_run`, the single run
writer (INV-1/INV-2). There is deliberately no second write path here.

Confirm is idempotent on COROS `label_id` (INV-5): `confirm_run` is a no-op when
`activities.coros_activity_id` already exists, and this module then simply marks
the pending row confirmed. So a retry after a crash between "run logged" and
"row marked" cannot double-log: the second call finds the run already logged and
only completes the bookkeeping. (`confirm_run` commits its own transaction, so
the two steps are two commits made safe by that idempotency, not one.)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import OwnedShoe, PendingCorosRun
from app.services import coros as coros_svc
from app.utils.activity_tags import is_valid_tag
from app.utils.pace import seconds_to_pace


def pending_to_dict(row: PendingCorosRun) -> dict:
    return {
        "id": row.id,
        "label_id": row.label_id,
        "run_date": row.run_date.isoformat(),
        "distance_km": row.distance_km,
        "avg_pace": seconds_to_pace(row.avg_pace_s_per_km),
        "avg_pace_s_per_km": row.avg_pace_s_per_km,
        "avg_hr": row.avg_hr,
        "moving_time_s": row.moving_time_s,
        "elapsed_time_s": row.elapsed_time_s,
        "elevation_gain_m": row.elevation_gain_m,
        "calories": row.calories,
        "avg_cadence": row.avg_cadence,
        "training_load": row.training_load,
        "training_focus": row.training_focus,
        "location_label": row.location_label,   # label only; coordinates stay out of API/MCP payloads
        "suggested_shoe_id": row.suggested_shoe_id,
        "suggestion_reason": row.suggestion_reason,
        "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
    }


def list_pending(db: Session) -> list[dict]:
    """Pending runs, newest first (date, then start time)."""
    rows = (
        db.query(PendingCorosRun)
        .filter(PendingCorosRun.status == "pending")
        .order_by(PendingCorosRun.run_date.desc(), PendingCorosRun.start_timestamp.desc())
        .all()
    )
    return [pending_to_dict(r) for r in rows]


def _get(db: Session, pending_id: int) -> PendingCorosRun:
    row = db.get(PendingCorosRun, pending_id)
    if row is None:
        raise LookupError(f"Pending COROS run {pending_id} not found")
    return row


def confirm(
    db: Session,
    pending_id: int,
    *,
    owned_shoe_id: int,
    activity_tag: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Log a pending run to `owned_shoe_id` (the runner's choice; the stored
    suggestion is only a default) and mark it confirmed.

    Returns {"logged": bool, "already_logged": bool, shoe..., threshold...}.
    Raises LookupError (unknown pending run / shoe), ValueError (dismissed run,
    invalid tag). Commits.
    """
    row = _get(db, pending_id)
    if row.status == "confirmed":
        return {"logged": False, "already_logged": True, "shoe": None,
                "checkpoint_reached": False, "checkpoint_km": None,
                "threshold_crossed": None, "threshold_message": None}
    if row.status == "dismissed":
        raise ValueError("This run was dismissed")
    if activity_tag is not None and not is_valid_tag(activity_tag):
        raise ValueError(f"'{activity_tag}' is not a valid activity_tag")

    shoe = db.get(OwnedShoe, owned_shoe_id)
    if shoe is None:
        raise LookupError(f"Owned shoe {owned_shoe_id} not found")

    result = coros_svc.confirm_run(
        db,
        coros_activity_id=row.label_id,
        owned_shoe_id=owned_shoe_id,
        run_date=row.run_date,
        distance_km=row.distance_km,
        avg_pace=seconds_to_pace(row.avg_pace_s_per_km),
        avg_hr=row.avg_hr,
        notes=notes,
        elevation_gain_m=row.elevation_gain_m,
        moving_time_s=row.moving_time_s,
        elapsed_time_s=row.elapsed_time_s,
        avg_cadence=row.avg_cadence,
        calories=row.calories,
        training_load=row.training_load,
        training_focus=row.training_focus,
        activity_tag=activity_tag,
        start_lat=row.start_lat,
        start_lng=row.start_lng,
        location_label=row.location_label,
    )

    row.status = "confirmed"
    row.resolved_at = datetime.now(timezone.utc)
    db.commit()

    if result is None:   # already logged by another path (Claude / earlier crash): bookkeeping only
        return {"logged": False, "already_logged": True, "shoe": None,
                "checkpoint_reached": False, "checkpoint_km": None,
                "threshold_crossed": None, "threshold_message": None}

    return {
        "logged": True,
        "already_logged": False,
        "shoe": {"id": result.shoe.id, "brand": result.shoe.brand, "model": result.shoe.model,
                 "new_mileage": round(result.shoe.current_mileage, 2)},
        "checkpoint_reached": result.checkpoint_reached,
        "checkpoint_km": result.checkpoint_km,
        "threshold_crossed": result.threshold_crossed,
        "threshold_message": result.threshold_message,
    }


def dismiss(db: Session, pending_id: int) -> dict:
    """Mark a pending run dismissed (it shouldn't count toward any shoe). The row
    is kept so the poller never re-queues it. Idempotent; a confirmed run can't
    be dismissed (ValueError). Commits."""
    row = _get(db, pending_id)
    if row.status == "confirmed":
        raise ValueError("This run is already logged")
    if row.status != "dismissed":
        row.status = "dismissed"
        row.resolved_at = datetime.now(timezone.utc)
        db.commit()
    return {"dismissed": True}
