"""
Auth administration (R9.2) — "sign out everywhere" and a counts-only status.

Scope: browser sessions (`services/sessions.py`) and the OAuth connector
(`services/oauth.py` tokens + auth codes). Named bearer tokens from
`ANTON_TOKENS` are untouched by design: they are static config that does not
derive from the login password, so rotating them is an env-file edit, not a
runtime action.

Like `sessions.py` / `oauth.py`, the functions here open their own DB sessions
(via those modules) rather than taking a `db` argument, because the auth
services sit beside the ASGI middleware, outside FastAPI dependency injection.
Each revoke commits on its own.

Deliberately not exposed over MCP: auth administration is not an AI-callable
capability.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services import oauth, sessions

logger = logging.getLogger(__name__)


@dataclass
class SignOutResult:
    sessions_revoked: int
    oauth_tokens_revoked: int


def sign_out_everywhere(*, source: str) -> SignOutResult:
    """
    End every browser session and every OAuth token/auth code.

    `source` identifies the trigger for the audit log (a client IP, or "cli").
    Logs at WARNING with both counts. Not atomic across the two stores (each
    commits independently); both deletes are idempotent, so re-running is safe.
    """
    result = SignOutResult(
        sessions_revoked=sessions.revoke_all(),
        oauth_tokens_revoked=oauth.revoke_all(),
    )
    logger.warning(
        "sign-out-everywhere from %s: %d session(s), %d oauth token(s) revoked",
        source, result.sessions_revoked, result.oauth_tokens_revoked,
    )
    return result


def security_status() -> dict:
    """Counts-only status: unexpired session count and whether a connector is live."""
    return {
        "active_sessions": sessions.count_active(),
        "connector_connected": oauth.has_active_connector(),
    }
