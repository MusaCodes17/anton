"""
COROS direct-sync connection endpoints (R5.7 §2). Thin: HTTP <-> services.coros_connection.

  POST /api/coros/connect   session/bearer-auth — returns {authorize_url}
  GET  /api/coros/callback  PUBLIC (browser redirect from COROS) — protected by the
                            single-use OAuth `state`; redirects into the SPA
  GET  /api/coros/status    session/bearer-auth — connection state, no tokens

All but the callback are gated by the app-wide auth middleware. Disconnect
(DELETE) is intentionally absent pending the runner's go-ahead (auth-touching).
"""
import logging
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import coros_connection as conn

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
    return conn.get_status(db)
