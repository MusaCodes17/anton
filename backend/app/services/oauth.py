"""
OAuth 2.1 authorization-server provider (RA1.1b — Path 1).

Single-user Anton implementation of mcp.server.auth.provider.OAuthAuthorizationServerProvider.
The SDK (mcp.server.auth) handles all protocol-level work:
  - /authorize, /token, /.well-known/oauth-authorization-server (routes.py)
  - PKCE S256 verification in TokenHandler (we store the challenge; SDK verifies)
  - redirect_uri exact-match validation in AuthorizationHandler
  - all OAuth error response formats

This module owns:
  - The static client registry (one client read from ANTON_OAUTH_* env vars)
  - Auth code + token persistence (oauth_auth_codes, oauth_tokens tables)
  - Token issuance, rotation, and revocation
  - The login-redirect target: authorize() returns /oauth/login?<all params>

Security properties:
  - Auth codes: 256-bit random (token_hex(32)); stored as SHA-256 hex; 60-second TTL.
  - Single-use: exchange_authorization_code marks code as used before issuing tokens.
  - Access tokens: 256-bit random; stored as SHA-256 hex; 1-hour expiry.
  - Refresh tokens: 256-bit random; stored as SHA-256 hex; 30-day expiry; rotated on use.
  - Revocation: pair_id ties both tokens; revoking one deletes both.
  - The login password is compared with secrets.compare_digest (timing-safe).

Design_decisions reference: E9 (RA1.1b — Path 1 chosen; capability-URL deleted).
"""
from __future__ import annotations

import hashlib
import os
import secrets
import time
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from pydantic import AnyUrl
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import OAuthAuthCode, OAuthToken
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken as OAuthTokenResponse

# Access token lifetime: 1 hour.  Refresh tokens: 30 days.
_ACCESS_TOKEN_TTL = 3600
_REFRESH_TOKEN_TTL = 30 * 24 * 3600


def _hash(token: str) -> str:
    """SHA-256 hex digest of a raw token string."""
    return hashlib.sha256(token.encode()).hexdigest()


def _db() -> Session:
    """Return a fresh SQLAlchemy session; caller must close it."""
    return SessionLocal()


def get_static_client() -> OAuthClientInformationFull | None:
    """
    Return the one statically-registered OAuth client from env vars, or None
    if ANTON_OAUTH_CLIENT_ID is not set (connector not configured).

    No Dynamic Client Registration — the connector is registered once in .env.
    """
    client_id = os.getenv("ANTON_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("ANTON_OAUTH_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("ANTON_OAUTH_REDIRECT_URI", "").strip()

    if not client_id or not redirect_uri:
        return None

    return OAuthClientInformationFull(
        client_id=client_id,
        client_secret=client_secret or None,
        redirect_uris=[AnyUrl(redirect_uri)],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        # No scope restriction — the connector can request any scope.
        scope=None,
    )


class AntonOAuthProvider:
    """
    Single-user OAuthAuthorizationServerProvider for the Anton MCP server.

    Satisfies the mcp.server.auth.provider.OAuthAuthorizationServerProvider
    Protocol without explicit inheritance (structural subtyping).
    """

    # ------------------------------------------------------------------ #
    # Client registry (static — no DCR)                                   #
    # ------------------------------------------------------------------ #

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Return the registered client if client_id matches; None otherwise."""
        client = get_static_client()
        if client is None or client.client_id != client_id:
            return None
        return client

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """DCR is disabled — the connector is statically registered in .env."""
        raise NotImplementedError("Dynamic Client Registration is not supported")

    # ------------------------------------------------------------------ #
    # Authorization flow                                                   #
    # ------------------------------------------------------------------ #

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """
        Return the URL of the login page with all OAuth params forwarded as
        query parameters.  The AuthorizationHandler redirects the browser there.
        The login page renders a password form; on success, it writes an auth
        code row and redirects to redirect_uri?code=...&state=...

        All params land in the URL (not in session state) because:
          - code_challenge is not secret (secrecy is in the client's code_verifier)
          - single-user, TLS-protected, no adversary between server and browser
          - stateless approach avoids any temporary storage
        """
        query: dict[str, str] = {
            "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": "1" if params.redirect_uri_provided_explicitly else "0",
            "client_id": client.client_id,
        }
        if params.state:
            query["state"] = params.state
        if params.scopes:
            query["scope"] = " ".join(params.scopes)
        if params.resource:
            query["resource"] = params.resource
        return "/oauth/login?" + urlencode(query)

    # ------------------------------------------------------------------ #
    # Auth code lifecycle                                                  #
    # ------------------------------------------------------------------ #

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        """
        Look up an auth code by its raw value.  Returns None if not found,
        already used, or expired (SDK also checks expiry; belt-and-braces).
        """
        code_hash = _hash(authorization_code)
        db = _db()
        try:
            row = db.query(OAuthAuthCode).filter_by(code_hash=code_hash).first()
            if row is None or row.used or row.expires_at < time.time():
                return None
            return AuthorizationCode(
                code=authorization_code,
                scopes=row.scopes.split() if row.scopes else [],
                expires_at=row.expires_at,
                client_id=row.client_id,
                code_challenge=row.code_challenge,
                redirect_uri=AnyUrl(row.redirect_uri),
                redirect_uri_provided_explicitly=row.redirect_uri_provided_explicitly,
                resource=row.resource,
            )
        finally:
            db.close()

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthTokenResponse:
        """
        Mark the auth code as used (preventing replay), issue an access token
        and a refresh token, return the OAuthToken response.

        Both tokens share a pair_id so that revoking one revokes both.
        """
        code_hash = _hash(authorization_code.code)
        db = _db()
        try:
            row = db.query(OAuthAuthCode).filter_by(code_hash=code_hash).first()
            if row is None or row.used:
                raise TokenError(error="invalid_grant", error_description="authorization code already used")

            # Mark used before issuing tokens (atomic for single-process).
            row.used = True
            db.commit()

            access_raw = secrets.token_hex(32)
            refresh_raw = secrets.token_hex(32)
            pair_id = secrets.token_hex(16)
            now = time.time()
            scopes_str = " ".join(authorization_code.scopes) if authorization_code.scopes else None

            db.add(OAuthToken(
                token_hash=_hash(access_raw),
                token_type="access",
                client_id=client.client_id,
                scopes=scopes_str,
                expires_at=now + _ACCESS_TOKEN_TTL,
                resource=authorization_code.resource,
                pair_id=pair_id,
            ))
            db.add(OAuthToken(
                token_hash=_hash(refresh_raw),
                token_type="refresh",
                client_id=client.client_id,
                scopes=scopes_str,
                expires_at=now + _REFRESH_TOKEN_TTL,
                resource=authorization_code.resource,
                pair_id=pair_id,
            ))
            db.commit()

            return OAuthTokenResponse(
                access_token=access_raw,
                token_type="Bearer",
                expires_in=_ACCESS_TOKEN_TTL,
                refresh_token=refresh_raw,
                scope=scopes_str,
            )
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Refresh token lifecycle                                              #
    # ------------------------------------------------------------------ #

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        """Look up a refresh token by its raw value."""
        token_hash = _hash(refresh_token)
        db = _db()
        try:
            row = db.query(OAuthToken).filter_by(
                token_hash=token_hash, token_type="refresh"
            ).first()
            if row is None:
                return None
            if row.expires_at and row.expires_at < time.time():
                return None
            return RefreshToken(
                token=refresh_token,
                client_id=row.client_id,
                scopes=row.scopes.split() if row.scopes else [],
                expires_at=int(row.expires_at) if row.expires_at else None,
            )
        finally:
            db.close()

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthTokenResponse:
        """
        Rotate both tokens: delete the old pair and issue a new access+refresh pair.
        Rotation limits exposure if a refresh token is ever stolen.
        """
        old_hash = _hash(refresh_token.token)
        db = _db()
        try:
            old_row = db.query(OAuthToken).filter_by(token_hash=old_hash).first()
            if old_row is None:
                raise TokenError(error="invalid_grant", error_description="refresh token not found")

            old_pair_id = old_row.pair_id

            # Delete the old pair before issuing new tokens.
            if old_pair_id:
                db.query(OAuthToken).filter_by(pair_id=old_pair_id).delete()
            else:
                db.delete(old_row)
            db.commit()

            access_raw = secrets.token_hex(32)
            refresh_raw = secrets.token_hex(32)
            pair_id = secrets.token_hex(16)
            now = time.time()
            scopes_str = " ".join(scopes) if scopes else None

            db.add(OAuthToken(
                token_hash=_hash(access_raw),
                token_type="access",
                client_id=client.client_id,
                scopes=scopes_str,
                expires_at=now + _ACCESS_TOKEN_TTL,
                pair_id=pair_id,
            ))
            db.add(OAuthToken(
                token_hash=_hash(refresh_raw),
                token_type="refresh",
                client_id=client.client_id,
                scopes=scopes_str,
                expires_at=now + _REFRESH_TOKEN_TTL,
                pair_id=pair_id,
            ))
            db.commit()

            return OAuthTokenResponse(
                access_token=access_raw,
                token_type="Bearer",
                expires_in=_ACCESS_TOKEN_TTL,
                refresh_token=refresh_raw,
                scope=scopes_str,
            )
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Access token verification (called by the SDK's bearer-auth path)    #
    # ------------------------------------------------------------------ #

    async def load_access_token(self, token: str) -> AccessToken | None:
        """
        Verify an access token and return its metadata if valid.
        Called by the SDK's bearer-auth middleware when checking MCP requests
        that arrive with an Authorization: Bearer <OAuth-issued token> header.
        """
        token_hash = _hash(token)
        db = _db()
        try:
            row = db.query(OAuthToken).filter_by(
                token_hash=token_hash, token_type="access"
            ).first()
            if row is None:
                return None
            if row.expires_at and row.expires_at < time.time():
                return None
            return AccessToken(
                token=token,
                client_id=row.client_id,
                scopes=row.scopes.split() if row.scopes else [],
                expires_at=int(row.expires_at) if row.expires_at else None,
                resource=row.resource,
            )
        finally:
            db.close()

    # ------------------------------------------------------------------ #
    # Revocation                                                           #
    # ------------------------------------------------------------------ #

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """
        Delete the token and its pair.  No-op if not found (already revoked).
        """
        token_hash = _hash(token.token)
        db = _db()
        try:
            row = db.query(OAuthToken).filter_by(token_hash=token_hash).first()
            if row is None:
                return
            if row.pair_id:
                db.query(OAuthToken).filter_by(pair_id=row.pair_id).delete()
            else:
                db.delete(row)
            db.commit()
        finally:
            db.close()


# Singleton provider instance (single-process by INV-9).
_provider: AntonOAuthProvider | None = None


def get_provider() -> AntonOAuthProvider:
    global _provider
    if _provider is None:
        _provider = AntonOAuthProvider()
    return _provider


def verify_access_token_sync(raw_token: str) -> bool:
    """
    Synchronous DB check for a raw OAuth access token.  Used by the ASGI auth
    middleware (which runs before FastAPI's dependency injection) to verify
    tokens issued by the OAuth server as an alternative to named bearer tokens.

    Returns True only if the token hash exists in oauth_tokens with type='access'
    and has not expired.
    """
    token_hash = _hash(raw_token)
    now = time.time()
    db = _db()
    try:
        row = db.query(OAuthToken).filter_by(
            token_hash=token_hash, token_type="access"
        ).first()
        if row is None:
            return False
        if row.expires_at and row.expires_at < now:
            return False
        return True
    except Exception:
        return False
    finally:
        db.close()


def create_auth_code(
    *,
    client_id: str,
    code_challenge: str,
    redirect_uri: str,
    redirect_uri_provided_explicitly: bool,
    scopes: str | None,
    resource: str | None,
) -> str:
    """
    Generate a 256-bit authorization code, persist its hash to the DB, and
    return the raw value to be forwarded to the client via redirect.

    Called by the login page handler after password verification succeeds (C9).
    Auth codes expire in 60 seconds — enough for the browser redirect round-trip.
    """
    raw = secrets.token_hex(32)
    db = _db()
    try:
        db.add(OAuthAuthCode(
            code_hash=_hash(raw),
            client_id=client_id,
            code_challenge=code_challenge,
            redirect_uri=redirect_uri,
            redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
            scopes=scopes,
            resource=resource,
            expires_at=time.time() + 60,
            used=False,
        ))
        db.commit()
    finally:
        db.close()
    return raw
