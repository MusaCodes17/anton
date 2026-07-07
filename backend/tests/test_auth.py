"""
HTTP-layer tests for the R2.1 bearer-token auth middleware
(app/middleware/auth.py). These are the suite's first tests that exercise the
real ASGI routing stack — the middleware is only meaningful through it.

Two environment notes:
- `ANTON_SECRET` is set *before* importing `app.main` so the middleware (which
  reads the secret once when the stack is built) and the lifespan fail-fast see
  it. `load_dotenv(override=False)` inside main won't clobber it.
- The installed httpx (0.28) dropped Starlette `TestClient`'s `app=` shortcut,
  so we drive the app via `httpx.ASGITransport` + `AsyncClient`, run through
  `asyncio.run` in plain sync test functions (no pytest-asyncio needed).

`get_db` is overridden with a throwaway in-memory SQLite session so the few
*authenticated* requests that reach a route never touch the live DB.
"""
import os

TEST_SECRET = "test-anton-secret-0123456789abcdef"
os.environ["ANTON_SECRET"] = TEST_SECRET  # must precede the app import below

import asyncio  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: E402,F401 — registers tables on Base.metadata

# In-memory DB for the authenticated requests that actually reach a route.
# StaticPool + check_same_thread=False keeps every connection pointed at the
# *same* in-memory database, so the tables created here are visible to the route
# handler even though FastAPI runs it in a threadpool worker (a fresh :memory:
# connection per thread would otherwise see an empty, table-less database).
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
    # The LLM-proxy: rejected before any provider call, so no key/spend needed.
    r = call("POST", "/api/chat/message", json={"messages": [], "model": "x"})
    assert r.status_code == 401


def test_owned_shoes_delete_requires_token():
    assert call("DELETE", "/api/owned-shoes/1").status_code == 401


def test_admin_scrape_lock_release_requires_token():
    # §4.7: the M3 admin force-release is now behind the token via the middleware.
    assert call("POST", "/api/admin/scrape-lock/release").status_code == 401


def test_mcp_mount_requires_token():
    # §4 open-question Q4: a top-level middleware must cover the mounted /mcp app.
    r = call("POST", "/mcp", json={}, headers={"Content-Type": "application/json"})
    assert r.status_code == 401


def test_wrong_token_rejected():
    assert call("GET", "/api/owned-shoes", token="not-the-secret").status_code == 401


def test_unauthorized_body_is_empty():
    # 401 leaks nothing — no reason string, no path-existence signal.
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


# --- Authenticated requests pass the gate -------------------------------------

def test_owned_shoes_list_authorized():
    # With the right token the request clears auth and reaches the route
    # (empty in-memory DB → 200 []). The point is: not 401.
    r = call("GET", "/api/owned-shoes", token=TEST_SECRET, follow=True)
    assert r.status_code != 401
    assert r.status_code == 200


def test_options_preflight_not_blocked():
    # CORS preflight must never require the token or the browser preflight breaks.
    r = call(
        "OPTIONS",
        "/api/owned-shoes",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code != 401
