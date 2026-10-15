"""
R9.1 gate regression test: the public surface is a pinned allowlist.

Anton has no per-route auth; `BearerAuthMiddleware` gates everything except
`PUBLIC_PATHS`. That makes the allowlist the single point where a route can
accidentally become world-readable, so this module ratchets it:

- `test_public_paths_pinned` — the allowlist equals a literal copy kept here.
  Widening it must touch this test on purpose (R9.1).
- `test_every_non_public_route_requires_auth` — walks every registered route
  (APIRoute, plain Route, Mount incl. `/mcp`) and asserts a credential-less
  request to each non-public (method, path) answers 401. One run reports every
  hole, so a future session adding an ungated route (or a middleware bypass)
  fails loudly instead of silently shipping.

Harness notes (mirrors test_auth.py): ANTON_TOKENS is set before importing
app.main; the app is driven via httpx.ASGITransport + asyncio.run; get_db is
overridden with an in-memory StaticPool DB (no request should reach a route
anyway). The per-IP auth-failure limiter turns repeated 401s into 429s, so each
request carries a distinct X-Forwarded-For (which `_client_ip` honours) and
gets its own bucket. OPTIONS is skipped: it passes through by design.
"""
import os
import re

# Must precede the app.main import (middleware reads the token map at build).
os.environ.setdefault("ANTON_TOKENS", "desktop:test-public-surface-token-0123456789")

import asyncio  # noqa: E402

import httpx  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.middleware.auth import PUBLIC_PATHS  # noqa: E402
from app.models import models  # noqa: E402,F401 — registers tables on Base.metadata

# Adding a public path must touch this test on purpose (R9.1): every entry here
# is an unauthenticated entry point to the backend and deserves a review.
EXPECTED_PUBLIC_PATHS = frozenset({
    "/",
    "/health",
    "/api/health",
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource",
    "/api/coros/callback",
    "/authorize",
    "/token",
    "/revoke",
    "/oauth/login",
    "/api/auth/session",
})

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


_PARAM_RE = re.compile(r"\{[^}]+\}")  # {name} and {name:converter}


def _concrete(path: str) -> str:
    return _PARAM_RE.sub("1", path)


def _walk_targets() -> list[tuple[str, str]]:
    """(method, concrete path) for every non-public, non-OPTIONS route."""
    targets: list[tuple[str, str]] = []
    for route in app.routes:
        if isinstance(route, Mount):
            base = _concrete(route.path)
            paths = [base, base + "/"]
            methods = ["GET", "POST"]
        elif isinstance(route, (APIRoute, Route)):
            paths = [_concrete(route.path)]
            methods = sorted(route.methods or [])
        else:
            continue
        for path in paths:
            if path in PUBLIC_PATHS:
                continue
            for method in methods:
                if method == "OPTIONS":
                    continue
                targets.append((method, path))
    return targets


def test_public_paths_pinned():
    assert PUBLIC_PATHS == EXPECTED_PUBLIC_PATHS, (
        "PUBLIC_PATHS changed. If intentional, update EXPECTED_PUBLIC_PATHS in "
        "tests/test_public_surface.py (R9.1) after reviewing the new exposure. "
        f"added={sorted(PUBLIC_PATHS - EXPECTED_PUBLIC_PATHS)} "
        f"removed={sorted(EXPECTED_PUBLIC_PATHS - PUBLIC_PATHS)}"
    )


def test_every_non_public_route_requires_auth():
    app.dependency_overrides[get_db] = _override_get_db
    targets = _walk_targets()

    async def _run() -> list[str]:
        failures: list[str] = []
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            for i, (method, path) in enumerate(targets):
                # Distinct client IP per request: separate limiter bucket, so a
                # 429 can never mask a missing gate (or replace a real 401).
                ip = f"10.0.{i // 250}.{i % 250}"
                r = await client.request(
                    method, path, headers={"X-Forwarded-For": ip}
                )
                if r.status_code != 401:
                    failures.append(f"{method} {path} -> {r.status_code}")
        return failures

    try:
        failures = asyncio.run(_run())
    finally:
        app.dependency_overrides.pop(get_db, None)

    # Guard against a vacuous pass (empty/partial enumeration).
    assert len(targets) > 50, f"route walk too small: {len(targets)}"
    assert ("GET", "/api/owned-shoes/") in targets or (
        "GET", "/api/owned-shoes") in targets
    assert ("POST", "/mcp") in targets and ("POST", "/mcp/") in targets

    assert not failures, "Routes reachable without credentials:\n" + "\n".join(failures)
