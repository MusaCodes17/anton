"""
COROS connection — Anton as an OAuth 2.1 client of the COROS MCP server
(COROS direct sync §2, roadmap R5.7; spike findings in docs/spikes/coros_mcp_client.md).

Job: own the OAuth connect flow (Dynamic Client Registration + PKCE), encrypted
token storage, and lazy/locked token refresh. It speaks OAuth only — MCP calls
live in the §3 client, which asks this module for an access token.

Facts this encodes (all from the spike):
- Open DCR, public client (no secret). client_id is registered once and stored;
  re-registered if the redirect URI changes.
- Access token ~30 days; **the refresh token rotates on every refresh**. So a
  refresh is serialized by `_refresh_lock` and the new refresh token is committed
  before the access token is handed to anyone. Two racing refreshes would burn
  the rotated token and force a reconnect. (INV-9: one process, so a
  threading.Lock is sufficient.) Residual risk, accepted: if the response to a
  refresh is lost after COROS rotated, the stored token is dead -> reauth_required.
- `resource` is sent on authorize/token requests (worked in the spike).

Failure policy: a 4xx from the token endpoint (invalid_grant etc.) means the
credential is dead -> status=reauth_required, stop. Network/5xx errors propagate
as requests exceptions with the status untouched (the poller backs off; no retry
storm here). Tokens are encrypted/decrypted ONLY in this module and never logged.

Commit ownership: functions here commit their own writes (connection state is
self-contained; there is no caller transaction to join).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.models.models import CorosConnection, CorosOAuthState

logger = logging.getLogger(__name__)

DEFAULT_MCP_URL = "https://mcpus.coros.com/mcp"
SCOPE = "openid mcp.tools offline_access"
STATE_TTL_S = 600            # a human signs in within minutes; short TTL limits replay
REFRESH_SKEW_S = 300         # refresh when <5 min of life remains
HTTP_TIMEOUT_S = 20
_CONNECTION_ID = 1

STATUS_CONNECTED = "connected"
STATUS_REAUTH = "reauth_required"
STATUS_DISCONNECTED = "disconnected"

# One lock for every refresh (poller, manual sync-now). See module docstring.
_refresh_lock = threading.Lock()
_as_metadata_cache: dict[str, dict] = {}


class CorosNotConfigured(Exception):
    """COROS_TOKEN_KEY is missing/invalid — the feature is disabled, not broken."""


class CorosAuthError(Exception):
    """No usable credential: not connected, or COROS rejected it (reconnect needed)."""


# ---------------------------------------------------------------- config / crypto

def mcp_url() -> str:
    return os.getenv("COROS_MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL


def _issuer(url: str) -> str:
    """https://mcpus.coros.com/mcp -> https://mcpus.coros.com"""
    from urllib.parse import urlparse
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def redirect_uri() -> str:
    explicit = os.getenv("COROS_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    host = os.getenv("ANTON_HOST_URL", "").strip().rstrip("/") or "http://localhost:8000"
    return f"{host}/api/coros/callback"


def frontend_url() -> str:
    return (os.getenv("FRONTEND_URL", "").strip()
            or os.getenv("ANTON_HOST_URL", "").strip()
            or "http://localhost:5173").rstrip("/")


def is_configured() -> bool:
    try:
        _fernet()
        return True
    except CorosNotConfigured:
        return False


def _fernet() -> Fernet:
    key = os.getenv("COROS_TOKEN_KEY", "").strip()
    if not key:
        raise CorosNotConfigured("COROS_TOKEN_KEY is not set")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise CorosNotConfigured("COROS_TOKEN_KEY is not a valid Fernet key") from exc


def _enc(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def _dec(blob: str) -> str:
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except InvalidToken as exc:
        # Key changed/rotated: stored tokens are unreadable -> user must reconnect.
        raise CorosAuthError("Stored COROS tokens can't be decrypted (key changed); reconnect") from exc


# ---------------------------------------------------------------- HTTP seam (tests patch these)

def _http_get_json(url: str) -> dict:
    r = requests.get(url, timeout=HTTP_TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def _http_post(url: str, *, json: Optional[dict] = None, data: Optional[dict] = None) -> requests.Response:
    return requests.post(url, json=json, data=data, timeout=HTTP_TIMEOUT_S)


def _as_metadata() -> dict:
    """Authorization-server metadata (cached per issuer; discovery per RFC 8414)."""
    issuer = _issuer(mcp_url())
    if issuer not in _as_metadata_cache:
        _as_metadata_cache[issuer] = _http_get_json(f"{issuer}/.well-known/oauth-authorization-server")
    return _as_metadata_cache[issuer]


# ---------------------------------------------------------------- row helpers

def _row(db: Session) -> Optional[CorosConnection]:
    return db.get(CorosConnection, _CONNECTION_ID)


def _row_or_create(db: Session) -> CorosConnection:
    row = _row(db)
    if row is None:
        row = CorosConnection(id=_CONNECTION_ID, status=STATUS_DISCONNECTED)
        db.add(row)
        db.flush()
    return row


def _now() -> float:
    return time.time()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- connect flow

def start_connect(db: Session) -> str:
    """
    Begin the connect flow: ensure a registered client, create single-use
    state + PKCE verifier (stored server-side), and return the authorize URL.

    Raises CorosNotConfigured (no encryption key) or requests.RequestException
    (COROS unreachable) — the router maps these to 503 / 502.
    """
    _fernet()  # fail before any network call or DB write if we couldn't store tokens
    meta = _as_metadata()
    row = _row_or_create(db)
    redir = redirect_uri()

    if not row.client_id or row.registered_redirect_uri != redir:
        resp = _http_post(meta["registration_endpoint"], json={
            "client_name": "Anton",
            "redirect_uris": [redir],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        })
        resp.raise_for_status()
        row.client_id = resp.json()["client_id"]
        row.registered_redirect_uri = redir
    row.region_endpoint = mcp_url()

    # Opportunistic cleanup so abandoned flows don't accumulate.
    db.query(CorosOAuthState).filter(CorosOAuthState.expires_at < _now()).delete()

    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(24)
    db.add(CorosOAuthState(state=state, code_verifier_enc=_enc(verifier), expires_at=_now() + STATE_TTL_S))
    db.commit()

    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return f"{meta['authorization_endpoint']}?" + urlencode({
        "response_type": "code",
        "client_id": row.client_id,
        "redirect_uri": redir,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": mcp_url(),
    })


def complete_connect(db: Session, *, state: str, code: str) -> None:
    """
    Callback half: validate + consume `state`, exchange the code, store tokens.

    The state is deleted *before* the exchange, so a replayed callback can never
    exchange twice. Raises ValueError for a bad/expired/replayed state or a
    rejected code (message is safe to surface as a short reason), and lets
    requests exceptions propagate for network errors.
    """
    st = db.get(CorosOAuthState, state) if state else None
    if st is None or st.expires_at < _now():
        if st is not None:
            db.delete(st)
            db.commit()
        raise ValueError("invalid_state")
    verifier = _dec(st.code_verifier_enc)
    db.delete(st)
    db.commit()

    row = _row(db)
    if row is None or not row.client_id:
        raise ValueError("not_registered")

    meta = _as_metadata()
    resp = _http_post(meta["token_endpoint"], data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": row.registered_redirect_uri,
        "client_id": row.client_id,
        "code_verifier": verifier,
        "resource": mcp_url(),
    })
    if 400 <= resp.status_code < 500:
        row.last_error = "authorization code rejected by COROS"
        db.commit()
        raise ValueError("exchange_rejected")
    resp.raise_for_status()
    _store_tokens(row, resp.json(), fresh_connect=True)
    db.commit()
    logger.info("COROS connected (scopes=%s)", row.scopes)


def _store_tokens(row: CorosConnection, tok: dict, *, fresh_connect: bool = False) -> None:
    """Persist a token response onto the row (caller commits). COROS rotates the
    refresh token; if a response ever omits it, keep the one we have."""
    row.access_token_enc = _enc(tok["access_token"])
    if tok.get("refresh_token"):
        row.refresh_token_enc = _enc(tok["refresh_token"])
    row.expires_at = _now() + float(tok.get("expires_in", 0))
    row.scopes = tok.get("scope") or row.scopes
    row.status = STATUS_CONNECTED
    row.last_error = None
    if fresh_connect:
        row.connected_at = _utcnow()
    else:
        row.last_refresh_at = _utcnow()


# ---------------------------------------------------------------- tokens

def get_access_token(db: Session) -> str:
    """
    Return a currently-valid access token, refreshing first if it's within
    REFRESH_SKEW_S of expiry. This is what the §3 client calls.

    Raises CorosAuthError when not connected / reauth is required (poller stops),
    CorosNotConfigured without a key, requests exceptions on transient failures.
    """
    row = _row(db)
    if row is None or row.status != STATUS_CONNECTED or not row.access_token_enc:
        raise CorosAuthError("COROS is not connected")
    if row.expires_at is None or row.expires_at - _now() <= REFRESH_SKEW_S:
        return refresh(db)
    return _dec(row.access_token_enc)


def refresh(db: Session, *, force: bool = False) -> str:
    """
    Refresh under the lock and return the new access token.

    Re-reads the row inside the lock: a concurrent caller may have already
    rotated the token while we waited, in which case we use its result instead
    of burning the (now stale) refresh token we saw earlier. `force` skips that
    freshness shortcut (manual/test use).
    """
    with _refresh_lock:
        db.expire_all()
        row = _row(db)
        if row is None or row.status != STATUS_CONNECTED or not row.refresh_token_enc:
            raise CorosAuthError("COROS is not connected")
        if not force and row.expires_at and row.expires_at - _now() > REFRESH_SKEW_S:
            return _dec(row.access_token_enc)

        meta = _as_metadata()
        resp = _http_post(meta["token_endpoint"], data={
            "grant_type": "refresh_token",
            "refresh_token": _dec(row.refresh_token_enc),
            "client_id": row.client_id,
            "resource": mcp_url(),
        })
        if 400 <= resp.status_code < 500:
            row.status = STATUS_REAUTH
            row.last_error = f"refresh rejected by COROS (HTTP {resp.status_code})"
            db.commit()
            logger.warning("COROS refresh rejected (HTTP %s); reauth required", resp.status_code)
            raise CorosAuthError("COROS refresh token was rejected; reconnect needed")
        resp.raise_for_status()  # 5xx -> propagate, status untouched
        _store_tokens(row, resp.json())
        db.commit()
        return _dec(row.access_token_enc)


def mark_reauth_required(db: Session, reason: str) -> None:
    """Called by the client when COROS rejects a fresh access token with 401."""
    row = _row(db)
    if row is not None and row.status == STATUS_CONNECTED:
        row.status = STATUS_REAUTH
        row.last_error = reason[:500]
        db.commit()


# ---------------------------------------------------------------- status

def get_status(db: Session) -> dict:
    """Connection state for the UI. Never includes tokens or the client id."""
    row = _row(db)
    return {
        "configured": is_configured(),
        "status": row.status if row else STATUS_DISCONNECTED,
        "connected_at": row.connected_at.isoformat() if row and row.connected_at else None,
        "last_refresh_at": row.last_refresh_at.isoformat() if row and row.last_refresh_at else None,
        "token_expires_at": (datetime.fromtimestamp(row.expires_at, timezone.utc).isoformat()
                             if row and row.expires_at else None),
        "scopes": row.scopes.split() if row and row.scopes else [],
        "last_error": row.last_error if row else None,
    }
