"""
Tests for R9.2 "sign out everywhere": services/auth_admin.py, the two
/api/auth endpoints, and the revoke/count helpers in sessions.py and oauth.py.

Harness: same ASGI approach as test_auth.py. A private in-memory DB is swapped
into `sessions` and `oauth` per test via monkeypatch (so other modules' import-
time patches are restored afterwards).
"""
import asyncio
import hashlib
import os
import time

# Identical to test_auth.py's assignment (same value, so import order is moot):
# the middleware reads the map once, when the stack is first built.
NAMED_TOKEN = "test-anton-secret-0123456789abcdef"
os.environ["ANTON_TOKENS"] = (
    f"desktop:{NAMED_TOKEN},spa:test-other-secret-0123456789abcd00"
)
HOST = "https://test.example.com"  # ANTON_HOST_URL from conftest
PASSWORD = "sign-out-test-password"

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: E402
import app.routers.session as session_router  # noqa: E402
import app.services.oauth as oauth_svc  # noqa: E402
import app.services.sessions as sessions_svc  # noqa: E402
from app.services import auth_admin  # noqa: E402
from app.services.rate_limit import KeyedRateLimiter  # noqa: E402


@pytest.fixture
def S(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    maker = sessionmaker(bind=engine)
    monkeypatch.setattr(sessions_svc, "SessionLocal", maker)
    monkeypatch.setattr(oauth_svc, "SessionLocal", maker)
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: iter([maker()]))
    monkeypatch.setenv("ANTON_LOGIN_PASSWORD", PASSWORD)
    monkeypatch.setattr(session_router, "_login_failure_limiter",
                        KeyedRateLimiter(capacity=1000, refill_per_s=1000))
    # These tests make many deliberate 401s from one IP; the shared auth-failure
    # limiter would start answering 429 (and poison other modules' tests).
    from app.services.rate_limit import auth_failure_limiter
    auth_failure_limiter._buckets.clear()
    yield maker
    auth_failure_limiter._buckets.clear()


def call(method, path, *, cookie=None, token=None, origin=None, **kw):
    headers = dict(kw.pop("headers", {}))
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    cookies = {"anton_session": cookie} if cookie else None

    async def _body():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies=cookies
        ) as client:
            return await client.request(method, path, headers=headers, **kw)

    return asyncio.run(_body())


def login() -> str:
    r = call("POST", "/api/auth/session", json={"password": PASSWORD})
    assert r.status_code == 200
    return r.cookies["anton_session"]


def sign_out(cookie):
    return call("POST", "/api/auth/sign-out-everywhere", cookie=cookie, origin=HOST)


def add_oauth_token(maker, raw="tok-1", token_type="access", expires_in=3600.0):
    db = maker()
    db.add(models.OAuthToken(
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        token_type=token_type, client_id="c",
        expires_at=None if expires_in is None else time.time() + expires_in,
    ))
    db.commit()
    db.close()


def add_code(maker):
    db = maker()
    db.add(models.OAuthAuthCode(
        code_hash="h" * 64, client_id="c", code_challenge="x",
        redirect_uri="https://x/cb", redirect_uri_provided_explicitly=True,
        expires_at=time.time() + 600, used=False,
    ))
    db.commit()
    db.close()


def test_session_cookie_dead_after_sign_out(S):
    cookie = login()
    assert call("GET", "/api/auth/security", cookie=cookie).status_code == 200
    r = sign_out(cookie)
    assert r.status_code == 200
    assert call("GET", "/api/auth/security", cookie=cookie).status_code == 401


def test_other_sessions_also_revoked(S):
    other = login()
    mine = login()
    r = sign_out(mine)
    assert r.json()["sessions_revoked"] == 2
    assert call("GET", "/api/auth/security", cookie=other).status_code == 401


def test_oauth_token_and_codes_revoked(S):
    add_oauth_token(S, "tok-1")
    add_oauth_token(S, "ref-1", "refresh", None)
    add_code(S)
    assert oauth_svc.verify_access_token_sync("tok-1") is True
    cookie = login()
    r = sign_out(cookie)
    assert r.json()["oauth_tokens_revoked"] == 2
    assert oauth_svc.verify_access_token_sync("tok-1") is False
    db = S()
    assert db.query(models.OAuthToken).count() == 0
    assert db.query(models.OAuthAuthCode).count() == 0
    db.close()


def test_named_bearer_token_survives(S):
    cookie = login()
    sign_out(cookie)
    assert call("GET", "/api/auth/security", token=NAMED_TOKEN).status_code == 200


def test_post_logged_out_is_401(S):
    r = call("POST", "/api/auth/sign-out-everywhere", origin=HOST)
    assert r.status_code == 401


def test_post_cross_origin_is_403_and_revokes_nothing(S):
    cookie = login()
    r = call("POST", "/api/auth/sign-out-everywhere", cookie=cookie,
             origin="https://evil.example.com")
    assert r.status_code == 403
    assert sessions_svc.count_active() == 1


def test_response_clears_cookie(S):
    cookie = login()
    r = sign_out(cookie)
    sc = r.headers.get("set-cookie", "")
    assert "anton_session=" in sc
    lowered = sc.lower()
    assert 'max-age=0' in lowered or "expires=" in lowered
    assert cookie not in sc


def test_security_endpoint_counts(S):
    c1 = login()
    login()
    r = call("GET", "/api/auth/security", cookie=c1)
    assert r.json() == {"active_sessions": 2, "connector_connected": False}
    add_oauth_token(S)
    r = call("GET", "/api/auth/security", cookie=c1)
    assert r.json()["connector_connected"] is True


def test_security_requires_auth(S):
    assert call("GET", "/api/auth/security").status_code == 401


def test_service_counts_and_expiry_rules(S):
    sessions_svc.create_session()
    sessions_svc.create_session()
    db = S()
    db.add(models.AuthSession(session_hash="e" * 64, expires_at=time.time() - 10))
    db.commit()
    db.close()
    assert sessions_svc.count_active() == 2  # expired row excluded

    # Expired access token alone: not connected. Non-expiring refresh: connected.
    add_oauth_token(S, "old", "access", -10)
    assert oauth_svc.has_active_connector() is False
    add_oauth_token(S, "ref", "refresh", None)
    assert oauth_svc.has_active_connector() is True

    add_code(S)
    res = auth_admin.sign_out_everywhere(source="cli")
    assert res.sessions_revoked == 3  # includes the expired row
    assert res.oauth_tokens_revoked == 2
    assert auth_admin.security_status() == {
        "active_sessions": 0, "connector_connected": False,
    }
    # Idempotent second run.
    again = auth_admin.sign_out_everywhere(source="cli")
    assert (again.sessions_revoked, again.oauth_tokens_revoked) == (0, 0)


def test_sign_out_logs_warning_with_source(S, caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="app.services.auth_admin"):
        auth_admin.sign_out_everywhere(source="cli")
    assert any("cli" in r.message for r in caplog.records)
