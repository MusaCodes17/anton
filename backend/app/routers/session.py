"""
SPA session-cookie auth endpoints (RA2.1).

These retire the baked-in `spa` bearer token: the built SPA bundle carries no
secret, and the user logs in with a password to receive an httpOnly session
cookie that gates `/api`.

  POST   /api/auth/session  — public. Validate the password (same timing-safe
                              compare + per-IP throttle as /oauth/login), then
                              set the `anton_session` cookie and return 200.
  DELETE /api/auth/session  — clear the cookie and delete the session row (logout).
  GET    /api/auth/session  — public. Return {authenticated: bool} so the SPA can
                              decide login-vs-app on load.

This is a *third* credential type alongside named bearer tokens and OAuth 2.1
access tokens — it does not touch the /mcp mount or the OAuth connector flow.
The password is `ANTON_LOGIN_PASSWORD`, the same secret the OAuth login page
uses (C9): a personal single-user platform has one owner and one password.
"""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.middleware.auth import _client_ip as _get_client_ip
from app.services.rate_limit import login_failure_limiter
from app.services.sessions import (
    create_session,
    delete_session,
    session_ttl_seconds,
    verify_session_sync,
)

logger = logging.getLogger(__name__)

# Module-level reference so tests can monkeypatch it (mirrors routers/oauth.py).
_login_failure_limiter = login_failure_limiter

SESSION_COOKIE = "anton_session"

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SessionLogin(BaseModel):
    password: str = ""


@router.post("/session")
async def create_session_endpoint(body: SessionLogin, request: Request, response: Response):
    """
    Validate the password and, on success, set the session cookie.

    RA1.3 parity: the per-IP `login_failure_limiter` is checked before any
    password work, so a brute-force attempt is throttled after the burst is
    exhausted (429 + Retry-After). The password is compared with
    `secrets.compare_digest` (timing-safe); a wrong password returns 401 with a
    generic message (C9 — no oracle).
    """
    ip = _get_client_ip(request.scope)

    rl = _login_failure_limiter.take(ip)
    if not rl.allowed:
        retry = str(max(1, int(rl.retry_after_s)))
        logger.warning("session login rate-limited from %s", ip)
        return Response(status_code=429, headers={"Retry-After": retry})

    expected = os.getenv("ANTON_LOGIN_PASSWORD", "").strip()
    if not expected:
        # Login unconfigured — refuse rather than allow an empty-password bypass.
        return Response(status_code=503, content="Login is not configured on this server.")

    if not secrets.compare_digest(body.password.encode(), expected.encode()):
        logger.warning("session login failed from %s", ip)
        return Response(status_code=401)

    raw = create_session()
    # httpOnly (JS can't read it) + Secure (HTTPS only) + SameSite=Lax (first
    # line of CSRF defence; the middleware's Origin check is defence-in-depth) +
    # Path=/ so it rides every /api request.
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw,
        max_age=session_ttl_seconds(),
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return {"success": True}


@router.delete("/session")
async def delete_session_endpoint(request: Request, response: Response):
    """Logout: delete the presented session row and clear the cookie."""
    raw = request.cookies.get(SESSION_COOKIE)
    if raw:
        delete_session(raw)
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"success": True}


@router.get("/session")
async def probe_session_endpoint(request: Request):
    """Public probe: does the caller hold a valid session cookie?"""
    raw = request.cookies.get(SESSION_COOKIE)
    authenticated = bool(raw) and verify_session_sync(raw)
    return {"authenticated": authenticated}
