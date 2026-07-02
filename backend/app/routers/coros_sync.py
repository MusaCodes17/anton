"""
API routes for COROS GPS watch sync.

Flow:
  1. GET  /status   — check credentials + last-sync time
  2. POST /fetch    — pull recent COROS runs, filter out already-logged ones
  3. POST /confirm  — accept user-assigned runs and log them to shoes

The user must explicitly confirm each assignment before any run is written
to the database. Nothing is auto-logged.
"""
from datetime import datetime
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.coros_client import get_coros_config
from app.database import get_db
from app.models.schemas import (
    CorosConfirmRequest,
    CorosConfirmResponse,
    CorosFetchResponse,
    CorosRun,
    CorosSyncStatus,
    OwnedShoeResponse,
)
from app.routers.owned_shoes import _attach_computed_fields
from app.services import coros as coros_svc, settings as settings_svc

router = APIRouter(prefix="/owned-shoes/sync-coros", tags=["coros-sync"])


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@router.get("/status", response_model=CorosSyncStatus)
def get_sync_status(db: Session = Depends(get_db)):
    """Return whether COROS credentials are configured and when we last synced."""
    config = get_coros_config()
    last_sync_str = settings_svc.get_setting(db, "last_coros_sync_at")
    last_sync_at = datetime.fromisoformat(last_sync_str) if last_sync_str else None
    return CorosSyncStatus(
        coros_configured=config is not None,
        last_sync_at=last_sync_at,
        pending_runs=0,
    )


@router.post("/fetch", response_model=CorosFetchResponse)
def fetch_coros_runs(days_back: int = 30, db: Session = Depends(get_db)):
    """
    Fetch recent runs from COROS and return those not yet logged.

    Query param `days_back` controls the lookback window (default 30 days).
    Returns an empty list (not an error) when COROS is not configured.
    """
    try:
        result = coros_svc.fetch_unsynced(db, days_back)
    except requests.exceptions.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"COROS API unreachable: {exc}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return CorosFetchResponse(
        runs=[CorosRun(**r) for r in result.runs],
        already_synced=result.already_synced,
        coros_configured=result.coros_configured,
    )


@router.post("/confirm", response_model=CorosConfirmResponse)
def confirm_coros_runs(body: CorosConfirmRequest, db: Session = Depends(get_db)):
    """
    Log user-confirmed COROS run → shoe assignments.

    Each assignment is written as a ShoeRun with source='coros'. Idempotent
    — double-submitting the same coros_activity_id is a no-op. Each run now
    also triggers checkpoint detection (previously missing on the REST path).
    """
    from datetime import date as date_type

    logged = 0
    updated_shoes: List[OwnedShoeResponse] = []

    for assignment in body.assignments:
        try:
            result = coros_svc.confirm_run(
                db,
                coros_activity_id=assignment.coros_activity_id,
                owned_shoe_id=assignment.owned_shoe_id,
                run_date=date_type.fromisoformat(assignment.date),
                distance_km=assignment.distance_km,
                avg_pace=assignment.avg_pace,
                avg_hr=assignment.avg_hr,
                notes=assignment.notes,
            )
        except LookupError:
            continue  # shoe not found — skip as before

        if result is None:
            continue  # already logged — idempotent skip

        logged += 1
        updated_shoes.append(_attach_computed_fields(db, result.shoe))

    return CorosConfirmResponse(logged=logged, updated_shoes=updated_shoes)
