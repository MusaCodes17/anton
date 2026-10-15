"""
R9.5 global login-failure ceiling, exercised through both password login
endpoints: `POST /api/auth/session` (routers/session.py) and `POST /oauth/login`
(routers/oauth.py).

The per-IP limiter catches one client guessing fast. The global ceiling catches
the distributed version: many IPs, each under its own bucket, collectively
guessing the one password. These tests pin two things:

  - once the ceiling is exhausted, the form refuses EVERY IP, including one that
    has never failed and presents the correct password (429);
  - only wrong passwords spend from the ceiling: correct logins never draw it
    down, so the owner is never locked out by someone else's failures while the
    bucket still has room.

Environment: ANTON_TOKENS and the OAuth vars are set before importing app.main,
as test_oauth.py does. The login password is set via monkeypatch per test.
"""
import os

os.environ.setdefault("ANTON_TOKENS", "desktop:test-anton-secret-0123456789abcdef")
os.environ["ANTON_HOST_URL"] = "https://test.example.com"
os.environ["ANTON_OAUTH_CLIENT_ID"] = "test-client"
os.environ["ANTON_OAUTH_REDIRECT_URI"] = "https://test.example.com/callback"

import asyncio  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: E402,F401 — registers tables on Base.metadata
import app.services.oauth as oauth_svc  # noqa: E402
import app.services.sessions as sessions_svc  # noqa: E402
import app.routers.oauth as oauth_router_mod  # noqa: E402
import app.routers.session as session_router_mod  # noqa: E402
from app.services.rate_limit import KeyedRateLimiter, TokenBucket  # noqa: E402

PASSWORD = "global-ceiling-test-password"

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=_engine)
_Session = sessionmaker(bind=_engine)


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch):
    """Point the auth services at this module's in-memory DB for each test only.

    Patched per test (not at import): test_auth.py and test_oauth.py patch the
    same service attributes with their own engines, and a module-level assignment
    here would silently redirect their session reads to the wrong database."""
    monkeypatch.setattr(oauth_svc, "SessionLocal", _Session)
    monkeypatch.setattr(sessions_svc, "SessionLocal", _Session)


def _call(method: str, path: str, *, ip: str, follow: bool = False, **kw):
    headers = dict(kw.pop("headers", {}))
    headers["X-Forwarded-For"] = ip

    async def _body():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=follow
        ) as client:
            return await client.request(method, path, headers=headers, **kw)

    return asyncio.run(_body())


def _oauth_form(password: str) -> dict:
    return {
        "password": password,
        "code_challenge": "cc",
        "redirect_uri": "https://test.example.com/callback",
        "redirect_uri_provided_explicitly": "1",
        "client_id": "test-client",
        "state": "",
        "scope": "",
        "resource": "",
    }


# Each endpoint: (name, how to attempt a login with a given password from an IP).
def _attempt_session(password: str, ip: str):
    return _call("POST", "/api/auth/session", ip=ip, json={"password": password})


def _attempt_oauth(password: str, ip: str):
    return _call("POST", "/oauth/login", ip=ip, data=_oauth_form(password))


ENDPOINTS = [
    pytest.param(_attempt_session, "session", id="session"),
    pytest.param(_attempt_oauth, "oauth", id="oauth"),
]


def _patch(monkeypatch, which: str, *, global_limiter):
    """Swap in the global ceiling under test plus a generous per-IP limiter, so
    only the global ceiling can be the thing that refuses a request."""
    mod = session_router_mod if which == "session" else oauth_router_mod
    monkeypatch.setattr(mod, "_login_global_limiter", global_limiter)
    monkeypatch.setattr(mod, "_login_failure_limiter",
                        KeyedRateLimiter(capacity=1000, refill_per_s=1000))
    monkeypatch.setenv("ANTON_LOGIN_PASSWORD", PASSWORD)


@pytest.mark.parametrize("attempt, which", ENDPOINTS)
def test_global_ceiling_refuses_correct_password_from_new_ip(monkeypatch, attempt, which):
    """3 wrong passwords from 3 different IPs exhaust a capacity-3 ceiling. A
    fourth IP that has never failed, presenting the CORRECT password, is refused."""
    _patch(monkeypatch, which,
           global_limiter=TokenBucket(capacity=3, refill_per_s=0.000001))

    for i in range(3):
        r = attempt("wrong", f"198.51.100.{i + 1}")
        assert r.status_code == 401

    r = attempt(PASSWORD, "203.0.113.99")
    assert r.status_code == 429
    assert "retry-after" in r.headers


@pytest.mark.parametrize("attempt, which", ENDPOINTS)
def test_correct_password_never_spends_global_ceiling(monkeypatch, attempt, which):
    """A capacity-1 ceiling survives five correct logins from five IPs: success
    spends nothing, so the single token is still there afterwards."""
    bucket = TokenBucket(capacity=1, refill_per_s=0.000001)
    _patch(monkeypatch, which, global_limiter=bucket)

    for i in range(5):
        r = attempt(PASSWORD, f"192.0.2.{i + 1}")
        assert r.status_code in (200, 302), r.status_code

    assert bucket.peek().allowed is True
    assert bucket.take().allowed is True


@pytest.mark.parametrize("attempt, which", ENDPOINTS)
def test_wrong_password_below_ceiling_still_401_not_429(monkeypatch, attempt, which):
    """While the ceiling has room, a wrong password gets the normal 401 (no
    oracle change), and the failure is what spends the token."""
    bucket = TokenBucket(capacity=2, refill_per_s=0.000001)
    _patch(monkeypatch, which, global_limiter=bucket)

    assert attempt("wrong", "198.51.100.50").status_code == 401
    assert bucket.peek().allowed is True          # one token left
    assert attempt("wrong", "198.51.100.51").status_code == 401
    assert bucket.peek().allowed is False         # now exhausted
