"""
Tests for the OAuth 2.1 authorization server (RA1.1b).

Covers the key security invariants:
  - Correct password → auth code issued, redirect to redirect_uri
  - Wrong password → 401, form re-rendered
  - Auth code replay rejected (exchange marks code used)
  - Expired auth code rejected
  - Expired access token rejected by verify_access_token_sync
  - Unknown token rejected
  - OAuth protocol paths (/authorize, /token, etc.) are public (no 401)
  - AntonOAuthProvider.get_client returns None for unregistered client_id

Tests NOT included here (handled by the mcp[cli] SDK's own test suite):
  - PKCE S256 mismatch rejection (TokenHandler does the SHA-256 verify)
  - redirect_uri exact-match rejection (AuthorizationHandler does the check)

Setup notes:
- `ANTON_TOKENS` must be set before importing `app.main` (test_auth.py may have
  already done this if pytest runs alphabetically and shares sys.modules). We use
  setdefault so we don't clobber a value already set by test_auth.py.
- OAuth service functions use `SessionLocal()` directly, bypassing FastAPI's
  `get_db` dependency. We patch `app.services.oauth.SessionLocal` to point at our
  test session factory so DB calls land in the in-memory DB.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("ANTON_TOKENS", "desktop:test-anton-secret-0123456789abcdef")
os.environ["ANTON_LOGIN_PASSWORD"] = "correct-horse-battery-staple"
os.environ["ANTON_HOST_URL"] = "https://test.example.com"
os.environ["ANTON_OAUTH_CLIENT_ID"] = "test-client"
os.environ["ANTON_OAUTH_REDIRECT_URI"] = "https://test.example.com/callback"

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: E402, F401 — registers tables on Base.metadata
import app.services.oauth as oauth_svc  # noqa: E402

# In-memory test DB (separate from the one test_auth.py may have created).
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=_engine)
_Session = sessionmaker(bind=_engine)


def _override_get_db():
    s = _Session()
    try:
        yield s
    finally:
        s.close()


app.dependency_overrides[get_db] = _override_get_db

# Redirect oauth service DB calls to the test DB.
oauth_svc.SessionLocal = _Session  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# ASGI helper                                                                  #
# --------------------------------------------------------------------------- #

def call(method: str, path: str, *, token: str | None = None, follow: bool = True, **kw):
    """Drive one request through the real ASGI app."""
    headers = dict(kw.pop("headers", {}))
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    async def _body():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=follow
        ) as client:
            return await client.request(method, path, headers=headers, **kw)

    return asyncio.run(_body())


# --------------------------------------------------------------------------- #
# Login page — GET renders the form                                            #
# --------------------------------------------------------------------------- #

def test_login_get_renders_form():
    r = call(
        "GET",
        "/oauth/login?code_challenge=abc&redirect_uri=https%3A%2F%2Ftest.example.com%2Fcallback"
        "&client_id=test-client&redirect_uri_provided_explicitly=1",
        follow=False,
    )
    assert r.status_code == 200
    assert b"<form" in r.content
    assert b'name="password"' in r.content
    assert b"abc" in r.content  # code_challenge forwarded as hidden input


def test_login_get_is_public():
    """The login page must be reachable without a Bearer token."""
    r = call("GET", "/oauth/login", follow=False)
    assert r.status_code != 401


# --------------------------------------------------------------------------- #
# Login page — POST wrong password → 401                                       #
# --------------------------------------------------------------------------- #

def test_login_post_wrong_password_returns_401():
    r = call(
        "POST",
        "/oauth/login",
        follow=False,
        data={
            "password": "wrong-password",
            "code_challenge": "cc",
            "redirect_uri": "https://test.example.com/callback",
            "redirect_uri_provided_explicitly": "1",
            "client_id": "test-client",
            "state": "s1",
            "scope": "",
            "resource": "",
        },
    )
    assert r.status_code == 401
    assert b"Incorrect password" in r.content


def test_login_post_wrong_password_rerenders_form():
    r = call(
        "POST",
        "/oauth/login",
        follow=False,
        data={
            "password": "bad",
            "code_challenge": "challenge-xyz",
            "redirect_uri": "https://test.example.com/callback",
            "redirect_uri_provided_explicitly": "1",
            "client_id": "test-client",
            "state": "",
            "scope": "",
            "resource": "",
        },
    )
    assert b"<form" in r.content
    assert b"challenge-xyz" in r.content  # params preserved in hidden inputs


# --------------------------------------------------------------------------- #
# Login page — POST correct password → redirect with code                      #
# --------------------------------------------------------------------------- #

def test_login_post_correct_password_redirects():
    r = call(
        "POST",
        "/oauth/login",
        follow=False,
        data={
            "password": "correct-horse-battery-staple",
            "code_challenge": "pkce-challenge",
            "redirect_uri": "https://test.example.com/callback",
            "redirect_uri_provided_explicitly": "1",
            "client_id": "test-client",
            "state": "my-state",
            "scope": "",
            "resource": "",
        },
    )
    assert r.status_code == 302
    location = r.headers["location"]
    assert "code=" in location
    assert "state=my-state" in location
    assert location.startswith("https://test.example.com/callback")


def test_login_post_correct_password_writes_code_to_db():
    """A successful login must create a usable auth code row."""
    from app.models.models import OAuthAuthCode
    r = call(
        "POST",
        "/oauth/login",
        follow=False,
        data={
            "password": "correct-horse-battery-staple",
            "code_challenge": "some-challenge",
            "redirect_uri": "https://test.example.com/callback",
            "redirect_uri_provided_explicitly": "1",
            "client_id": "test-client",
            "state": "",
            "scope": "mcp",
            "resource": "",
        },
    )
    assert r.status_code == 302
    location = r.headers["location"]
    code = dict(p.split("=", 1) for p in location.split("?", 1)[1].split("&"))["code"]
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    db = _Session()
    row = db.query(OAuthAuthCode).filter_by(code_hash=code_hash).first()
    db.close()
    assert row is not None
    assert not row.used
    assert row.scopes == "mcp"


# --------------------------------------------------------------------------- #
# Auth code replay rejection (INV-5 analogue for OAuth codes)                 #
# --------------------------------------------------------------------------- #

def test_exchange_marks_code_used_and_rejects_replay():
    """exchange_authorization_code must mark the code used; a second call raises."""
    import asyncio as _asyncio
    from mcp.shared.auth import OAuthClientInformationFull
    from pydantic import AnyUrl
    from mcp.server.auth.provider import AuthorizationCode
    from app.services.oauth import AntonOAuthProvider

    provider = AntonOAuthProvider()
    code = oauth_svc.create_auth_code(
        client_id="test-client",
        code_challenge="ch",
        redirect_uri="https://test.example.com/callback",
        redirect_uri_provided_explicitly=True,
        scopes=None,
        resource=None,
    )
    client = OAuthClientInformationFull(
        client_id="test-client",
        redirect_uris=[AnyUrl("https://test.example.com/callback")],
    )
    auth_code = AuthorizationCode(
        code=code,
        scopes=[],
        expires_at=time.time() + 60,
        client_id="test-client",
        code_challenge="ch",
        redirect_uri=AnyUrl("https://test.example.com/callback"),
        redirect_uri_provided_explicitly=True,
        resource=None,
    )

    # First exchange must succeed.
    token_resp = _asyncio.run(provider.exchange_authorization_code(client, auth_code))
    assert token_resp.access_token

    # Second exchange with the same code must fail (TokenError).
    from mcp.server.auth.provider import TokenError
    with pytest.raises(TokenError):
        _asyncio.run(provider.exchange_authorization_code(client, auth_code))


def test_load_authorization_code_returns_none_for_used_code():
    """load_authorization_code must return None after a code has been used."""
    import asyncio as _asyncio
    from mcp.shared.auth import OAuthClientInformationFull
    from pydantic import AnyUrl
    from mcp.server.auth.provider import AuthorizationCode
    from app.models.models import OAuthAuthCode
    from app.services.oauth import AntonOAuthProvider

    provider = AntonOAuthProvider()
    code = oauth_svc.create_auth_code(
        client_id="test-client",
        code_challenge="ch2",
        redirect_uri="https://test.example.com/callback",
        redirect_uri_provided_explicitly=True,
        scopes=None,
        resource=None,
    )
    # Mark it used directly.
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    db = _Session()
    row = db.query(OAuthAuthCode).filter_by(code_hash=code_hash).first()
    row.used = True
    db.commit()
    db.close()

    client = OAuthClientInformationFull(
        client_id="test-client",
        redirect_uris=[AnyUrl("https://test.example.com/callback")],
    )
    result = _asyncio.run(provider.load_authorization_code(client, code))
    assert result is None


# --------------------------------------------------------------------------- #
# Expired code rejected                                                        #
# --------------------------------------------------------------------------- #

def test_expired_code_not_returned_by_load():
    """load_authorization_code must return None for an expired code."""
    import asyncio as _asyncio
    from mcp.shared.auth import OAuthClientInformationFull
    from pydantic import AnyUrl
    from app.models.models import OAuthAuthCode
    from app.services.oauth import AntonOAuthProvider

    provider = AntonOAuthProvider()
    code = oauth_svc.create_auth_code(
        client_id="test-client",
        code_challenge="ch3",
        redirect_uri="https://test.example.com/callback",
        redirect_uri_provided_explicitly=True,
        scopes=None,
        resource=None,
    )
    # Force-expire the code.
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    db = _Session()
    row = db.query(OAuthAuthCode).filter_by(code_hash=code_hash).first()
    row.expires_at = time.time() - 1
    db.commit()
    db.close()

    client = OAuthClientInformationFull(
        client_id="test-client",
        redirect_uris=[AnyUrl("https://test.example.com/callback")],
    )
    # Our provider returns None for expired codes (belt-and-braces; SDK also checks).
    result = _asyncio.run(provider.load_authorization_code(client, code))
    assert result is None


# --------------------------------------------------------------------------- #
# verify_access_token_sync: expired and unknown tokens                         #
# --------------------------------------------------------------------------- #

def test_verify_access_token_unknown_returns_false():
    assert oauth_svc.verify_access_token_sync("not-a-real-token") is False


def test_verify_access_token_expired_returns_false():
    """An expired access token must be rejected."""
    import secrets as _secrets
    from app.models.models import OAuthToken

    raw = _secrets.token_hex(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    db = _Session()
    db.add(OAuthToken(
        token_hash=token_hash,
        token_type="access",
        client_id="test-client",
        expires_at=time.time() - 1,  # already expired
    ))
    db.commit()
    db.close()

    assert oauth_svc.verify_access_token_sync(raw) is False


def test_verify_access_token_valid_returns_true():
    """A valid, unexpired access token must be accepted."""
    import secrets as _secrets
    from app.models.models import OAuthToken

    raw = _secrets.token_hex(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    db = _Session()
    db.add(OAuthToken(
        token_hash=token_hash,
        token_type="access",
        client_id="test-client",
        expires_at=time.time() + 3600,
    ))
    db.commit()
    db.close()

    assert oauth_svc.verify_access_token_sync(raw) is True


# --------------------------------------------------------------------------- #
# get_client registry                                                           #
# --------------------------------------------------------------------------- #

def test_get_client_returns_none_for_wrong_client_id():
    import asyncio as _asyncio
    from app.services.oauth import AntonOAuthProvider

    provider = AntonOAuthProvider()
    result = _asyncio.run(provider.get_client("not-registered"))
    assert result is None


def test_get_client_returns_client_for_registered_id():
    import asyncio as _asyncio
    from app.services.oauth import AntonOAuthProvider

    provider = AntonOAuthProvider()
    result = _asyncio.run(provider.get_client("test-client"))
    assert result is not None
    assert result.client_id == "test-client"


# --------------------------------------------------------------------------- #
# OAuth public paths (no 401)                                                  #
# --------------------------------------------------------------------------- #

def test_oauth_login_path_is_public():
    r = call("GET", "/oauth/login", follow=False)
    assert r.status_code != 401


def test_well_known_oauth_path_is_public():
    """/.well-known/oauth-authorization-server must be reachable without a token."""
    r = call("GET", "/.well-known/oauth-authorization-server", follow=False)
    # Should get 200 (metadata doc) not 401.
    assert r.status_code != 401


def test_authorize_path_is_public():
    """The /authorize path should return an error about missing params, not 401."""
    r = call("GET", "/authorize", follow=False)
    assert r.status_code != 401


def test_token_path_is_public():
    """/token should return an OAuth error about missing params, not 401."""
    r = call("POST", "/token", follow=False, data={})
    assert r.status_code != 401
