"""
COROS direct-sync connection endpoints (R5.7 §2). Thin: HTTP <-> services.coros_connection.

  POST /api/coros/connect   session/bearer-auth — returns {authorize_url}
  GET  /api/coros/callback  PUBLIC (browser redirect from COROS) — protected by the
                            single-use OAuth `state`; redirects into the SPA
  GET  /api/coros/status    session/bearer-auth — connection state + sync summary, no tokens
  GET  /api/coros/pending + POST /api/coros/pending/{id}/confirm|dismiss — the inbox (§6)
  POST /api/coros/sync      session/bearer-auth — one poll now (writes only the pending queue)
  DELETE /api/coros/connection  session/bearer-auth — disconnect; {revoked_remotely}

All but the callback are gated by the app-wide auth middleware. DELETE /connection
(runner-approved 2026-10-07) forgets the tokens even if COROS can't revoke them.
"""
import logging
from urllib.parse import urlencode

import requests
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import coros_connection as conn, coros_inbox, coros_poller, schedule as schedule_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/coros", tags=["coros"])

# Where the browser lands after the callback (the SPA's sync settings screen).
_SETTINGS_PATH = "/settings/sync"


def _back(**params) -> RedirectResponse:
    return RedirectResponse(f"{conn.frontend_url()}{_SETTINGS_PATH}?{urlencode(params)}", status_code=302)


@router.post("/connect")
def connect(db: Session = Depends(get_db)):
    try:
        return {"authorize_url": conn.start_connect(db)}
    except conn.CorosNotConfigured as exc:
        raise HTTPException(status_code=503, detail=f"COROS sync is not configured: {exc}")
    except requests.RequestException as exc:
        logger.error("COROS connect failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="COROS is unreachable; try again shortly")


@router.get("/callback")
def callback(
    state: str = Query(""),
    code: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
):
    # `state` and `code` are redacted from access logs (middleware/access_log.py).
    if error:
        return _back(coros="error", reason="denied")
    if not code:
        return _back(coros="error", reason="invalid_state")
    try:
        conn.complete_connect(db, state=state, code=code)
    except ValueError as exc:
        return _back(coros="error", reason=str(exc))
    except (conn.CorosAuthError, conn.CorosNotConfigured):
        return _back(coros="error", reason="not_configured")
    except requests.RequestException as exc:
        logger.error("COROS callback exchange failed: %s", type(exc).__name__)
        return _back(coros="error", reason="unreachable")
    return _back(coros="connected")


@router.get("/status")
def status(db: Session = Depends(get_db)):
    """Connection state + last-sync summary + queue depth. No tokens."""
    return {
        **conn.get_status(db),
        "sync": coros_poller.get_sync_summary(db),
        "next_poll_utc": schedule_svc.get_coros_poll_next_run(),
    }


@router.post("/sync")
def sync_now(db: Session = Depends(get_db)):
    """Run one poll on demand (same code as the scheduled tick). Only writes the
    pending queue — never runs or mileage. 409 if not connected or a tick is running."""
    result = coros_poller.run_tick(db, trigger="manual")
    if result.skipped == "not_connected":
        raise HTTPException(status_code=409, detail="COROS is not connected")
    if result.skipped == "already_running":
        raise HTTPException(status_code=409, detail="A COROS sync is already in progress")
    return {"ok": result.ok, "found": result.found, "queued": result.queued, "errors": result.errors}


class ConfirmBody(BaseModel):
    owned_shoe_id: int
    activity_tag: Optional[str] = None
    notes: Optional[str] = None


@router.get("/pending")
def list_pending(db: Session = Depends(get_db)):
    """The "New runs" inbox: pending runs newest-first, plus when we last synced
    (the UI labels a cached list with it)."""
    summary = coros_poller.get_sync_summary(db)
    return {"runs": coros_inbox.list_pending(db), "last_success_at": summary["last_success_at"]}


@router.post("/pending/{pending_id}/confirm")
def confirm_pending(pending_id: int, body: ConfirmBody, db: Session = Depends(get_db)):
    """Log a pending run to the chosen shoe via the single run writer. Idempotent on label_id."""
    try:
        return coros_inbox.confirm(db, pending_id, owned_shoe_id=body.owned_shoe_id,
                                   activity_tag=body.activity_tag, notes=body.notes)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/pending/{pending_id}/dismiss")
def dismiss_pending(pending_id: int, db: Session = Depends(get_db)):
    try:
        return coros_inbox.dismiss(db, pending_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/connection")
def disconnect(db: Session = Depends(get_db)):
    """Delete stored tokens (and ask COROS to revoke them). Always succeeds locally;
    `revoked_remotely` says whether COROS honoured the revoke."""
    return conn.disconnect(db)
