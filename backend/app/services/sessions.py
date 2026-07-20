"""
SPA session store (RA2.1) — the third credential type.

After a password login the SPA holds an httpOnly `anton_session` cookie; this
module is the server side of that cookie. It deliberately mirrors the OAuth-token
pattern in `services/oauth.py`:

  - The session id is 256-bit random (`secrets.token_hex(32)`).
  - Only its SHA-256 hex digest is persisted (`sessions.session_hash`) — the raw
    value lives only in the browser, so a DB leak can't be replayed.
  - `verify_session_sync` is a *synchronous* DB check, called from the ASGI auth
    middleware (which runs before FastAPI dependency injection). Sync DB calls in
    an async context are acceptable here for the same reason as OAuth's
    `verify_access_token_sync`: single-user SQLite, sub-millisecond, no
    concurrency hazard under INV-9 (single worker).

This is transport auth only; it does not touch the /mcp mount, the OAuth 2.1
connector, or the named-bearer path — session auth is *additional*, not a
replacement (design_decisions E7/E9 remain in force for those clients).
"""
from __future__ import annotations

import hashlib
import os
import secrets
import time

from app.database import SessionLocal
from app.models.models import AuthSession

# Default session lifetime: 14 days. A single-user personal app wants a long-
# lived "stay signed in" cookie; tune via SESSION_TTL_DAYS.
_DEFAULT_TTL_DAYS = 14.0


def _hash(raw: str) -> str:
    """SHA-256 hex digest of a raw session id (same scheme as oauth tokens)."""
    return hashlib.sha256(raw.encode()).hexdigest()


def session_ttl_seconds() -> int:
    """Configured session lifetime in seconds (SESSION_TTL_DAYS, default 14)."""
    days = float(os.getenv("SESSION_TTL_DAYS", str(_DEFAULT_TTL_DAYS)))
    return int(days * 24 * 3600)


def create_session() -> str:
    """
    Generate a 256-bit session id, persist its hash with an expiry, and return
    the raw value to be set as the `anton_session` cookie.

    Called by `POST /api/auth/session` after the password check passes.
    """
    raw = secrets.token_hex(32)
    db = SessionLocal()
    try:
        db.add(AuthSession(
            session_hash=_hash(raw),
            expires_at=time.time() + session_ttl_seconds(),
        ))
        db.commit()
    finally:
        db.close()
    return raw


def verify_session_sync(raw: str) -> bool:
    """
    Synchronous DB check for a raw session id. Used by the ASGI auth middleware.

    Returns True only if the hash exists in `sessions` and has not expired.
    Any error (missing table during a partial migration, etc.) is treated as
    "not authorized" rather than raising into the middleware.
    """
    session_hash = _hash(raw)
    now = time.time()
    db = SessionLocal()
    try:
        row = db.query(AuthSession).filter_by(session_hash=session_hash).first()
        if row is None:
            return False
        if row.expires_at < now:
            return False
        return True
    except Exception:
        return False
    finally:
        db.close()


def delete_session(raw: str) -> None:
    """
    Delete the session row for a raw session id. No-op if not found (logout of
    an already-expired/unknown session is a silent success).
    """
    session_hash = _hash(raw)
    db = SessionLocal()
    try:
        db.query(AuthSession).filter_by(session_hash=session_hash).delete()
        db.commit()
    finally:
        db.close()
