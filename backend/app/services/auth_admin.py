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

import hashlib
import logging
import os
import secrets
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services import oauth, sessions
from app.services import settings as settings_svc

logger = logging.getLogger(__name__)

PASSWORD_FINGERPRINT_KEY = "login_password_fingerprint"  # AppSettings key (R9.2)
# scrypt cost parameters (the hashlib/RFC 7914 interactive-login defaults):
# ~16 MiB and tens of ms per guess — cheap once at boot, expensive to brute-force.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


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


def _fingerprint(password: str, salt: bytes) -> str:
    """`scrypt$<salt hex>$<digest hex>` for `password` under `salt`."""
    digest = hashlib.scrypt(
        password.encode(), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def _matches(password: str, stored: str) -> bool:
    """True iff `stored` is a fingerprint of `password`. Malformed -> False."""
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        bytes.fromhex(digest_hex)
    except ValueError:
        return False
    return secrets.compare_digest(_fingerprint(password, salt), stored)


def check_password_rotation(db: Session) -> bool:
    """
    Boot-time check (R9.2): sign out everywhere if ANTON_LOGIN_PASSWORD changed.

    Makes "change the password + recreate the container" the leaked-password
    playbook. Commits `db` itself when it writes a fingerprint. Returns True
    only when a rotation was detected and the purge ran.

    - Password unset/blank: login is unconfigured; do nothing, return False.
    - Nothing stored (first boot): store a fingerprint, no purge, return False.
    - Stored fingerprint matches: no-op, return False.
    - Mismatch (including a malformed stored value, treated as a change because
      failing safe means purging): sign out everywhere, store a new
      fingerprint, return True.

    Why scrypt with a random salt, not SHA-256: the DB is replicated to B2 by
    Litestream, so a fast unsalted hash of the passphrase sitting in a backup
    could be cracked offline. A slow salted KDF makes that impractical. The
    password and the fingerprint are never logged.
    """
    password = os.getenv("ANTON_LOGIN_PASSWORD", "").strip()
    if not password:
        return False

    stored = settings_svc.get_setting(db, PASSWORD_FINGERPRINT_KEY)
    if not stored:
        settings_svc.set_setting(
            db, PASSWORD_FINGERPRINT_KEY,
            _fingerprint(password, secrets.token_bytes(16)),
        )
        db.commit()
        logger.info("login password fingerprint recorded (first boot)")
        return False

    if _matches(password, stored):
        return False

    sign_out_everywhere(source="password-change")
    settings_svc.set_setting(
        db, PASSWORD_FINGERPRINT_KEY,
        _fingerprint(password, secrets.token_bytes(16)),
    )
    db.commit()
    logger.warning("login password changed — signed out everywhere")
    return True
