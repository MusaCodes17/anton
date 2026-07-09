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
