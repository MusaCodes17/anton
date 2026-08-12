"""
Tests for RA1.1c — public (PKCE-only) OAuth client support.

The claude.ai connector authenticates at /token as a PUBLIC client: PKCE only,
no client secret. Before RA1.1c, get_static_client() never set
token_endpoint_auth_method, so the SDK's ClientAuthenticator read it as None,
fell through every branch, and raised "Unsupported auth method: None" — blocking
the token exchange.

These tests pin the two-mode behavior:
  - No secret configured → auth method "none", client_secret None (public client)
  - Secret configured    → auth method "client_secret_post", secret round-trips
  - ClientAuthenticator accepts a public-client /token POST (client_id only, no
    Authorization header, no client_secret) without raising
  - GET /.well-known/oauth-authorization-server advertises "none"

Setup mirrors test_oauth.py: env vars are set before importing app.main, and the
oauth service's SessionLocal is redirected at the in-memory test DB.
"""
from __future__ import annotations

import asyncio
import os

import httpx

os.environ.setdefault("ANTON_TOKENS", "desktop:test-anton-secret-0123456789abcdef")
os.environ.setdefault("ANTON_LOGIN_PASSWORD", "correct-horse-battery-staple")
os.environ["ANTON_HOST_URL"] = "https://test.example.com"
os.environ["ANTON_OAUTH_CLIENT_ID"] = "test-client"
os.environ["ANTON_OAUTH_REDIRECT_URI"] = "https://test.example.com/callback"
# Ensure a clean starting state: no secret unless a test sets one.
os.environ.pop("ANTON_OAUTH_CLIENT_SECRET", None)

from app.main import app  # noqa: E402
import app.services.oauth as oauth_svc  # noqa: E402


# --------------------------------------------------------------------------- #
# ASGI helper                                                                  #
# --------------------------------------------------------------------------- #

def call(method: str, path: str, *, follow: bool = False, **kw):
    """Drive one request through the real ASGI app."""
    async def _body():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=follow
        ) as client:
            return await client.request(method, path, **kw)

    return asyncio.run(_body())


# --------------------------------------------------------------------------- #
# get_static_client — public vs confidential                                   #
# --------------------------------------------------------------------------- #

def test_no_secret_yields_public_client(monkeypatch):
    """With no secret in env, the static client is public: auth method 'none'."""
    monkeypatch.delenv("ANTON_OAUTH_CLIENT_SECRET", raising=False)
    client = oauth_svc.get_static_client()
    assert client is not None
    assert client.token_endpoint_auth_method == "none"
    assert client.client_secret is None


def test_secret_yields_confidential_client(monkeypatch):
    """With a secret in env, the static client is confidential and it round-trips."""
    monkeypatch.setenv("ANTON_OAUTH_CLIENT_SECRET", "s3cr3t-value")
    client = oauth_svc.get_static_client()
    assert client is not None
    assert client.token_endpoint_auth_method == "client_secret_post"
    assert client.client_secret == "s3cr3t-value"


# --------------------------------------------------------------------------- #
# ClientAuthenticator accepts a public-client /token POST                       #
# --------------------------------------------------------------------------- #

def test_client_authenticator_accepts_public_client(monkeypatch):
    """
    A public-client /token POST carries client_id only — no Authorization header,
    no client_secret. ClientAuthenticator must authenticate it without raising
    (the fix: token_endpoint_auth_method == "none" takes the skip-secret branch).
    """
    monkeypatch.delenv("ANTON_OAUTH_CLIENT_SECRET", raising=False)

    from mcp.server.auth.middleware.client_auth import ClientAuthenticator
    from starlette.requests import Request
    from urllib.parse import urlencode

    authenticator = ClientAuthenticator(oauth_svc.get_provider())

    body = urlencode({"client_id": "test-client"}).encode()

    async def _receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/token",
        "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        "query_string": b"",
    }
    request = Request(scope, _receive)

    client = asyncio.run(authenticator.authenticate_request(request))
    assert client.client_id == "test-client"
    assert client.token_endpoint_auth_method == "none"


# --------------------------------------------------------------------------- #
# AS metadata advertises "none"                                                #
# --------------------------------------------------------------------------- #

def test_metadata_advertises_none_auth_method():
    """
    GET /.well-known/oauth-authorization-server must list "none" in
    token_endpoint_auth_methods_supported so the connector knows it may
    authenticate as a public PKCE client.
    """
    r = call("GET", "/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    body = r.json()
    methods = body["token_endpoint_auth_methods_supported"]
    assert "none" in methods
    # The confidential methods stay advertised too.
    assert "client_secret_post" in methods
    assert "client_secret_basic" in methods
