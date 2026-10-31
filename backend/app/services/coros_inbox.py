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

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import OwnedShoe, PendingCorosRun
from app.services import coros as coros_svc
from app.services import coros_suggestion
from app.utils.activity_tags import is_valid_tag
from app.utils.pace import seconds_to_pace

logger = logging.getLogger(__name__)


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
        "distance_km": row.distance_km,
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


# --- compact view for Claude (R12 lean sync §T1) -------------------------------------

@dataclass
class InboxRun:
    pending_id: int
    date: str
    distance_km: float
    avg_pace: Optional[str]
    avg_hr: Optional[int]
    training_focus: Optional[str]
    suggested_shoe_id: Optional[int]
    suggested_shoe: Optional[str]
    suggestion_reason: Optional[str]
    suggestion_refreshed: bool = False


@dataclass
class RotationShoe:
    id: int
    name: str
    shoe_type: Optional[str]
    current_mileage_km: float


@dataclass
class InboxView:
    runs: list[InboxRun] = field(default_factory=list)
    rotation: list[RotationShoe] = field(default_factory=list)


def _shoe_name(shoe: OwnedShoe) -> str:
    # The runner refers to shoes by nickname, so show it alongside brand and model.
    base = f"{shoe.brand} {shoe.model}"
    return f"{base} ({shoe.nickname})" if shoe.nickname else base


def inbox_view(db: Session) -> InboxView:
    """
    Compact read-only view of the "New runs" inbox plus the active rotation.

    Read-only: never commits, never writes back. When a pending run's stored
    suggestion points at a shoe that is no longer active (retired, for_sale, or
    gone), the suggestion is recomputed for this view only and flagged with
    `suggestion_refreshed`. It is not written to the row: a suggestion is derived,
    so persisting the refresh would be a second writer for a derived value (INV-7 style).
    """
    active_rows = (
        db.query(OwnedShoe)
        .filter(OwnedShoe.status == "active")
        .order_by(OwnedShoe.id)
        .all()
    )
    active = {s.id: s for s in active_rows}
    rotation = [
        RotationShoe(
            id=s.id,
            name=_shoe_name(s),
            shoe_type=s.shoe_type,
            current_mileage_km=round(s.current_mileage or 0.0, 1),
        )
        for s in active_rows
    ]

    runs: list[InboxRun] = []
    for p in list_pending(db):
        stored_id = p["suggested_shoe_id"]
        refreshed = False
        if stored_id is None:
            shoe_id, reason = None, p["suggestion_reason"]
        elif stored_id in active:
            shoe_id, reason = stored_id, p["suggestion_reason"]
        else:
            sug = coros_suggestion.suggest_shoe(
                db,
                distance_km=p["distance_km"],
                avg_pace_s_per_km=p["avg_pace_s_per_km"],
            )
            shoe_id, reason = sug.shoe_id, sug.reason
            refreshed = True
        runs.append(InboxRun(
            pending_id=p["id"],
            date=p["run_date"],
            distance_km=p["distance_km"],
            avg_pace=p["avg_pace"],
            avg_hr=p["avg_hr"],
            training_focus=p["training_focus"],
            suggested_shoe_id=shoe_id,
            suggested_shoe=_shoe_name(active[shoe_id]) if shoe_id is not None else None,
            suggestion_reason=reason,
            suggestion_refreshed=refreshed,
        ))

    return InboxView(runs=runs, rotation=rotation)


# --- batch resolve (R12 lean sync §T2) ------------------------------------------------

@dataclass(frozen=True)
class BatchItem:
    pending_id: int
    action: str                          # "confirm" | "dismiss"
    owned_shoe_id: Optional[int] = None  # required for confirm: no default-to-suggestion (INV-8)
    activity_tag: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class BatchResult:
    logged: int = 0
    dismissed: int = 0
    already_logged: int = 0
    errors: list[dict] = field(default_factory=list)       # {pending_id, error}
    per_shoe: list[dict] = field(default_factory=list)     # {shoe_id, name, km_added, new_mileage_km}
    thresholds: list[dict] = field(default_factory=list)   # {shoe_id, name, threshold_km, message}
    checkpoints: list[dict] = field(default_factory=list)  # {shoe_id, name, checkpoint_km}


def resolve_batch(db: Session, items: list[BatchItem]) -> BatchResult:
    """
    Confirm/dismiss many pending runs in one call and summarize server-side.

    Loops over `confirm()` / `dismiss()` — no new write path (INV-2). Each item
    commits on its own (confirm/dismiss own the commits), so one bad item cannot
    roll back the others; a failed item is rolled back and reported in `errors`.
    Confirm requires an explicit `owned_shoe_id`: the stored suggestion is never
    used as a default (INV-8). Re-running a batch is safe (INV-5): confirmed rows
    count as `already_logged` and add nothing to `per_shoe`.

    Raises:
        ValueError: on duplicate pending_id, before any write.
    """
    ids = [i.pending_id for i in items]
    dupes = sorted({x for x in ids if ids.count(x) > 1})
    if dupes:
        raise ValueError(f"Duplicate pending_id in batch: {dupes}")

    result = BatchResult()
    km_added: dict[int, float] = {}      # insertion order = first-seen order
    new_mileage: dict[int, float] = {}
    thresholds: dict[int, int] = {}      # shoe_id -> latest crossing km
    threshold_msgs: dict[int, Optional[str]] = {}

    for item in items:
        try:
            if item.action == "confirm":
                if item.owned_shoe_id is None:
                    result.errors.append({"pending_id": item.pending_id,
                                          "error": "owned_shoe_id is required to confirm"})
                    continue
                out = confirm(db, item.pending_id, owned_shoe_id=item.owned_shoe_id,
                              activity_tag=item.activity_tag, notes=item.notes)
                if out["already_logged"]:
                    result.already_logged += 1
                    continue
                result.logged += 1
                sid = item.owned_shoe_id
                km_added[sid] = km_added.get(sid, 0.0) + (out["distance_km"] or 0.0)
                new_mileage[sid] = out["shoe"]["new_mileage"]
                if out["threshold_crossed"] is not None:
                    thresholds[sid] = out["threshold_crossed"]
                    threshold_msgs[sid] = out["threshold_message"]
                if out["checkpoint_reached"]:
                    result.checkpoints.append({"shoe_id": sid, "checkpoint_km": out["checkpoint_km"]})
            elif item.action == "dismiss":
                dismiss(db, item.pending_id)
                result.dismissed += 1
            else:
                result.errors.append({"pending_id": item.pending_id,
                                      "error": f"Unknown action '{item.action}'"})
        except (LookupError, ValueError) as exc:
            db.rollback()
            result.errors.append({"pending_id": item.pending_id, "error": str(exc)})
        except Exception:
            logger.exception("resolve_batch: unexpected failure for pending_id=%s action=%s",
                             item.pending_id, item.action)
            db.rollback()
            result.errors.append({"pending_id": item.pending_id, "error": "Internal error"})

    names: dict[int, str] = {}

    def name_of(sid: int) -> str:
        if sid not in names:
            shoe = db.get(OwnedShoe, sid)
            names[sid] = _shoe_name(shoe) if shoe is not None else f"Shoe {sid}"
        return names[sid]

    for sid, km in km_added.items():
        result.per_shoe.append({"shoe_id": sid, "name": name_of(sid),
                                "km_added": round(km, 2), "new_mileage_km": new_mileage[sid]})
    for sid, km in thresholds.items():
        result.thresholds.append({"shoe_id": sid, "name": name_of(sid),
                                  "threshold_km": km, "message": threshold_msgs[sid]})
    for cp in result.checkpoints:
        cp["name"] = name_of(cp["shoe_id"])
    return result
