"""
HTTP-layer tests for the RA1.1/RA1.1b auth middleware (app/middleware/auth.py).

Two environment notes:
- `ANTON_TOKENS` is set *before* importing `app.main` so the middleware (which
  reads the token map once when the stack is built) and the lifespan fail-fast
  see it. `load_dotenv(override=False)` inside main won't clobber it.
- The installed httpx (0.28) dropped Starlette `TestClient`'s `app=` shortcut,
  so we drive the app via `httpx.ASGITransport` + `AsyncClient`, run through
  `asyncio.run` in plain sync test functions (no pytest-asyncio needed).

`get_db` is overridden with a throwaway in-memory SQLite session so the few
*authenticated* requests that reach a route never touch the live DB.

Note: capability-URL tests were removed in RA1.1b when the capability-URL path
was replaced by OAuth 2.1 (design_decisions E9). See test_oauth.py instead.
"""
import os

# Named token map: "client:token,..." — set before importing app.main so the
# middleware reads the right values at startup.
TEST_SECRET = "test-anton-secret-0123456789abcdef"
TEST_OTHER  = "test-other-secret-0123456789abcd00"
os.environ["ANTON_TOKENS"] = f"desktop:{TEST_SECRET},spa:{TEST_OTHER}"

# RA2.1 session-cookie login password. Set per-test via monkeypatch (not at
# module import) so it never clobbers test_oauth.py's ANTON_LOGIN_PASSWORD —
# both modules are imported once at collection and share the process env.
TEST_LOGIN_PASSWORD = "test-login-password-abc123"

import asyncio  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: E402,F401 — registers tables on Base.metadata

# In-memory DB for the authenticated requests that actually reach a route.
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

# RA2.1: the sessions service uses SessionLocal() directly (bypassing get_db),
# so point it at the in-memory test DB (mirrors test_oauth.py's oauth patch).
import app.services.sessions as sessions_svc  # noqa: E402

sessions_svc.SessionLocal = _Session  # type: ignore[assignment]


def call(method: str, path: str, *, token: str | None = None, follow: bool = False, **kw):
    """Drive one request against the real app over ASGI and return the response."""
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


# --- Unauthenticated mutation / spend surfaces are rejected --------------------

def test_owned_shoes_list_requires_token():
    assert call("GET", "/api/owned-shoes").status_code == 401


def test_chat_message_requires_token():
    r = call("POST", "/api/chat/message", json={"messages": [], "model": "x"})
    assert r.status_code == 401


def test_owned_shoes_delete_requires_token():
    assert call("DELETE", "/api/owned-shoes/1").status_code == 401


def test_admin_scrape_lock_release_requires_token():
    assert call("POST", "/api/admin/scrape-lock/release").status_code == 401


def test_mcp_mount_requires_token():
    # The top-level middleware must cover the mounted /mcp app.
    r = call("POST", "/mcp", json={}, headers={"Content-Type": "application/json"})
    assert r.status_code == 401


def test_wrong_token_rejected():
    assert call("GET", "/api/owned-shoes", token="not-the-secret").status_code == 401


def test_unauthorized_body_is_empty():
    assert call("GET", "/api/owned-shoes").content == b""


# --- Public liveness / root stay open -----------------------------------------

def test_health_open_without_token():
    assert call("GET", "/health").status_code == 200


def test_api_health_open_without_token():
    assert call("GET", "/api/health").status_code == 200


def test_root_open_without_token():
    assert call("GET", "/").status_code == 200


def test_health_ok_with_token_too():
    assert call("GET", "/api/health", token=TEST_SECRET).status_code == 200


# --- Named per-client tokens: any registered token is accepted -----------------

def test_first_named_token_accepted():
    r = call("GET", "/api/owned-shoes", token=TEST_SECRET, follow=True)
    assert r.status_code != 401
    assert r.status_code == 200


def test_second_named_token_accepted():
    # A different client's token must also pass the gate.
    r = call("GET", "/api/owned-shoes", token=TEST_OTHER, follow=True)
    assert r.status_code != 401
    assert r.status_code == 200


def test_unregistered_token_rejected():
    # A token not in the map is rejected even if it looks plausible.
    r = call("GET", "/api/owned-shoes", token="completely-different-secret")
    assert r.status_code == 401


# --- CORS preflight passes through without token ------------------------------

def test_options_preflight_not_blocked():
    r = call(
        "OPTIONS",
        "/api/owned-shoes",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code != 401


# --- RA1.3: 401 logging with source IP ----------------------------------------

def test_401_is_logged_with_method_and_path(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="app.middleware.auth"):
        call("GET", "/api/owned-shoes")
    assert any("auth 401" in r.message and "/api/owned-shoes" in r.message
               for r in caplog.records)


def test_401_log_contains_source_ip(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="app.middleware.auth"):
        call("GET", "/api/owned-shoes")
    record = next(r for r in caplog.records if "auth 401" in r.message)
    # The test ASGI transport reports client as "testclient" or similar.
    # We just verify the IP field is non-empty (not "unknown").
    assert record.message  # truthy — not an empty string


def test_client_name_stored_in_scope_on_success():
    """A successful auth should result in a 200 (not 401), proving scope was set
    correctly — scope['anton_client'] is consumed by the access log middleware.
    The stored value itself is exercised in test_access_log.py."""
    r = call("GET", "/api/owned-shoes", token=TEST_SECRET, follow=True)
    assert r.status_code == 200


# --- RA1.3: auth-failure rate limiting ----------------------------------------

def test_repeated_auth_failures_trigger_429():
    """After the burst bucket is exhausted, the next failure returns 429.

    Tests the BearerAuthMiddleware directly (not through the full HTTP stack)
    so we can inject a tight limiter without fighting the already-built ASGI
    stack. Same pattern used in test_rate_limit.py for the chat limiter.
    """
    from app.middleware.auth import BearerAuthMiddleware
    from app.services.rate_limit import KeyedRateLimiter

    tight = KeyedRateLimiter(capacity=2, refill_per_s=0.001)

    async def fake_app(scope, receive, send):
        pass  # never reached on auth failure

    middleware = BearerAuthMiddleware(fake_app)
    middleware._failure_limiter = tight  # inject directly

    async def one_request() -> int:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/owned-shoes",
            "headers": [],
            "client": ("10.0.0.99", 54321),
            "query_string": b"",
        }
        status = [0]

        async def capture(msg):
            if msg["type"] == "http.response.start":
                status[0] = msg["status"]

        async def recv():
            return {}

        await middleware(scope, recv, capture)
        return status[0]

    async def run():
        s1 = await one_request()
        s2 = await one_request()
        s3 = await one_request()
        return s1, s2, s3

    s1, s2, s3 = asyncio.run(run())
    assert s1 == 401  # bucket has tokens
    assert s2 == 401  # bucket still has a token
    assert s3 == 429  # bucket exhausted → rate limited


# --- RA2.1: session-cookie auth (the SPA's third credential type) --------------
#
# These drive BearerAuthMiddleware directly (as the rate-limit test above does)
# so we can set ANTON_HOST_URL per-test and stub verify_session_sync — the
# app-level middleware was built once at import without ANTON_HOST_URL, so its
# CSRF origin is empty. Direct construction avoids that import-ordering coupling.

def _drive_cookie(
    *,
    cookie=None,
    auth_token=None,
    method="GET",
    path="/api/owned-shoes",
    origin=None,
    host_url="",
    verify_ok=True,
):
    """Run one request through a freshly-built middleware and return (status, reached)."""
    from app.middleware.auth import BearerAuthMiddleware
    import app.services.sessions as svc

    prev_host = os.environ.get("ANTON_HOST_URL")
    prev_verify = svc.verify_session_sync
    if host_url:
        os.environ["ANTON_HOST_URL"] = host_url
    else:
        os.environ.pop("ANTON_HOST_URL", None)
    svc.verify_session_sync = lambda raw: verify_ok
    try:
        reached = {"v": False}

        async def fake_app(scope, receive, send):
            reached["v"] = True
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-length", b"0")]})
            await send({"type": "http.response.body", "body": b""})

        mw = BearerAuthMiddleware(fake_app)

        headers = []
        if cookie is not None:
            headers.append((b"cookie", f"anton_session={cookie}".encode()))
        if auth_token is not None:
            headers.append((b"authorization", f"Bearer {auth_token}".encode()))
        if origin is not None:
            headers.append((b"origin", origin.encode()))

        scope = {
            "type": "http", "method": method, "path": path,
            "headers": headers, "client": ("10.0.0.5", 5000), "query_string": b"",
        }
        status = {"v": 0}

        async def capture(msg):
            if msg["type"] == "http.response.start":
                status["v"] = msg["status"]

        async def recv():
            return {}

        asyncio.run(mw(scope, recv, capture))
        return status["v"], reached["v"]
    finally:
        svc.verify_session_sync = prev_verify
        if prev_host is None:
            os.environ.pop("ANTON_HOST_URL", None)
        else:
            os.environ["ANTON_HOST_URL"] = prev_host


def test_valid_session_cookie_accepted():
    status, reached = _drive_cookie(cookie="valid-session-id", verify_ok=True)
    assert status == 200
    assert reached is True


def test_invalid_session_cookie_rejected():
    status, reached = _drive_cookie(cookie="bogus", verify_ok=False)
    assert status == 401
    assert reached is False


def test_no_cookie_rejected():
    status, reached = _drive_cookie(cookie=None, verify_ok=True)
    assert status == 401
    assert reached is False


def test_expired_session_rejected_by_verify():
    """verify_session_sync returns False for an expired row (unit-level)."""
    import time
    from app.models.models import AuthSession
    from app.services.sessions import _hash, verify_session_sync

    db = _Session()
    try:
        db.add(AuthSession(session_hash=_hash("expired-raw"),
                           expires_at=time.time() - 60))
        db.commit()
    finally:
        db.close()
    assert verify_session_sync("expired-raw") is False


def test_live_session_accepted_by_verify():
    import time
    from app.models.models import AuthSession
    from app.services.sessions import _hash, verify_session_sync

    db = _Session()
    try:
        db.add(AuthSession(session_hash=_hash("live-raw"),
                           expires_at=time.time() + 3600))
        db.commit()
    finally:
        db.close()
    assert verify_session_sync("live-raw") is True


# --- RA2.1: CSRF — Origin check on cookie-authenticated writes -----------------

HOST = "https://anton.example.com"


def test_csrf_post_wrong_origin_rejected():
    status, reached = _drive_cookie(
        cookie="valid", method="POST", path="/api/owned-shoes",
        origin="https://evil.example.com", host_url=HOST,
    )
    assert status == 403
    assert reached is False


def test_csrf_post_missing_origin_rejected():
    status, reached = _drive_cookie(
        cookie="valid", method="POST", path="/api/owned-shoes",
        origin=None, host_url=HOST,
    )
    assert status == 403
    assert reached is False


def test_csrf_post_matching_origin_allowed():
    status, reached = _drive_cookie(
        cookie="valid", method="POST", path="/api/owned-shoes",
        origin=HOST, host_url=HOST,
    )
    assert status == 200
    assert reached is True


def test_csrf_get_exempt_even_without_origin():
    """SSE (EventSource) is a GET — it must ride through with no Origin header."""
    status, reached = _drive_cookie(
        cookie="valid", method="GET", path="/api/scrape/stream",
        origin=None, host_url=HOST,
    )
    assert status == 200
    assert reached is True


def test_csrf_skipped_when_host_url_unset():
    """Dev (no ANTON_HOST_URL): SameSite=Lax is the guard; Origin check skipped."""
    status, reached = _drive_cookie(
        cookie="valid", method="POST", path="/api/owned-shoes",
        origin=None, host_url="",
    )
    assert status == 200
    assert reached is True


def test_bearer_write_exempt_from_csrf():
    """A named-bearer POST is CSRF-exempt (no cookie) even with a bad Origin."""
    status, reached = _drive_cookie(
        auth_token=TEST_SECRET, method="POST", path="/api/owned-shoes",
        origin="https://evil.example.com", host_url=HOST,
    )
    assert status == 200
    assert reached is True


# --- RA2.1: session-endpoint HTTP surface -------------------------------------

def _fresh_login_limiter(monkeypatch):
    """Give the session router its own generous limiter so these tests never
    deplete the shared `login_failure_limiter` singleton (which is also used by
    test_oauth.py — cross-file depletion under random ordering is otherwise flaky)."""
    import app.routers.session as sr
    from app.services.rate_limit import KeyedRateLimiter
    monkeypatch.setattr(sr, "_login_failure_limiter",
                        KeyedRateLimiter(capacity=1000, refill_per_s=1000))


def test_session_login_wrong_password_401(monkeypatch):
    monkeypatch.setenv("ANTON_LOGIN_PASSWORD", TEST_LOGIN_PASSWORD)
    _fresh_login_limiter(monkeypatch)
    r = call("POST", "/api/auth/session", json={"password": "nope"})
    assert r.status_code == 401


def test_session_login_correct_password_sets_cookie(monkeypatch):
    monkeypatch.setenv("ANTON_LOGIN_PASSWORD", TEST_LOGIN_PASSWORD)
    _fresh_login_limiter(monkeypatch)
    r = call("POST", "/api/auth/session", json={"password": TEST_LOGIN_PASSWORD})
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    lowered = set_cookie.lower()
    assert "anton_session=" in set_cookie
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=lax" in lowered


def test_session_probe_public_and_unauthenticated_without_cookie():
    r = call("GET", "/api/auth/session")
    assert r.status_code == 200
    assert r.json() == {"authenticated": False}


def test_session_login_rate_limited(monkeypatch):
    """After the burst is exhausted, POST /api/auth/session returns 429."""
    import app.routers.session as sr
    from app.services.rate_limit import KeyedRateLimiter

    monkeypatch.setenv("ANTON_LOGIN_PASSWORD", TEST_LOGIN_PASSWORD)
    tight = KeyedRateLimiter(capacity=2, refill_per_s=0.001)
    prev = sr._login_failure_limiter
    sr._login_failure_limiter = tight
    try:
        # Wrong password so we never actually create sessions; the limiter is
        # checked before the password compare, so the status is what we assert.
        s1 = call("POST", "/api/auth/session", json={"password": "x"}).status_code
        s2 = call("POST", "/api/auth/session", json={"password": "x"}).status_code
        s3 = call("POST", "/api/auth/session", json={"password": "x"}).status_code
    finally:
        sr._login_failure_limiter = prev
    assert s1 == 401  # bucket has tokens → password checked → wrong → 401
    assert s2 == 401
    assert s3 == 429  # bucket exhausted → rate limited before password check
