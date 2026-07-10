"""
Tests for the structured access log middleware (RA1.3 — app/middleware/access_log.py).

Covers:
  - One log line emitted per request (method, path, client, status, duration).
  - Sensitive query-string params are redacted (code, state, access_token, token,
    refresh_token).
  - Non-sensitive params are not redacted.
  - No request headers appear in the log (Authorization header especially).
  - Access log captures the client name from scope["anton_client"] set by auth.

All tests drive the middleware directly (not through the full HTTP stack) so they
are independent of auth state and the running ASGI app.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from app.middleware.access_log import AccessLogMiddleware, _redact_query


# --------------------------------------------------------------------------- #
# _redact_query unit tests                                                     #
# --------------------------------------------------------------------------- #

def test_redact_code_param():
    assert _redact_query("/authorize", "code=secret123") == "/authorize?code=***"


def test_redact_state_param():
    assert _redact_query("/cb", "state=csrf-token") == "/cb?state=***"


def test_redact_access_token_param():
    assert _redact_query("/api", "access_token=tok") == "/api?access_token=***"


def test_redact_token_param():
    assert _redact_query("/api", "token=abc") == "/api?token=***"


def test_redact_refresh_token_param():
    assert _redact_query("/api", "refresh_token=rt") == "/api?refresh_token=***"


def test_non_sensitive_param_not_redacted():
    assert _redact_query("/api", "limit=10") == "/api?limit=10"


def test_mixed_params_only_sensitive_redacted():
    result = _redact_query("/api", "limit=10&code=secret&page=2")
    assert "limit=10" in result
    assert "code=***" in result
    assert "page=2" in result
    assert "secret" not in result


def test_no_query_string_returns_path():
    assert _redact_query("/api/health", "") == "/api/health"


def test_empty_value_param_not_redacted():
    # An empty credential value is not a credential; key is kept as-is.
    assert _redact_query("/api", "code=") == "/api?code="


# --------------------------------------------------------------------------- #
# Middleware integration tests                                                 #
# --------------------------------------------------------------------------- #

def _make_scope(path="/api/health", qs=b"", client_name=None, method="GET"):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": qs,
        "headers": [],
        "client": ("127.0.0.1", 9999),
    }
    if client_name is not None:
        scope["anton_client"] = client_name
    return scope


async def _run_middleware(scope, *, response_status=200):
    """Run AccessLogMiddleware with a fake downstream that always returns 200."""
    log_lines = []

    async def fake_app(scope, receive, send):
        await send({"type": "http.response.start", "status": response_status, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def noop_send(msg):
        pass

    async def noop_recv():
        return {}

    middleware = AccessLogMiddleware(fake_app)
    await middleware(scope, noop_recv, noop_send)


def test_access_log_emits_one_line(caplog):
    with caplog.at_level(logging.INFO, logger="app.middleware.access_log"):
        asyncio.run(_run_middleware(_make_scope()))
    info_records = [r for r in caplog.records if r.name == "app.middleware.access_log"]
    assert len(info_records) == 1


def test_access_log_includes_method_path_status(caplog):
    with caplog.at_level(logging.INFO, logger="app.middleware.access_log"):
        asyncio.run(_run_middleware(_make_scope(path="/api/owned-shoes", method="GET")))
    msg = caplog.records[-1].message
    assert "GET" in msg
    assert "/api/owned-shoes" in msg
    assert "200" in msg


def test_access_log_includes_client_name(caplog):
    scope = _make_scope(client_name="desktop")
    with caplog.at_level(logging.INFO, logger="app.middleware.access_log"):
        asyncio.run(_run_middleware(scope))
    msg = caplog.records[-1].message
    assert "desktop" in msg


def test_access_log_defaults_to_anon_when_no_client(caplog):
    scope = _make_scope()  # no anton_client set
    with caplog.at_level(logging.INFO, logger="app.middleware.access_log"):
        asyncio.run(_run_middleware(scope))
    msg = caplog.records[-1].message
    assert "anon" in msg


def test_access_log_redacts_code_in_qs(caplog):
    scope = _make_scope(path="/token", qs=b"code=abc123&grant_type=authorization_code")
    with caplog.at_level(logging.INFO, logger="app.middleware.access_log"):
        asyncio.run(_run_middleware(scope))
    msg = caplog.records[-1].message
    assert "abc123" not in msg
    assert "code=***" in msg


def test_access_log_does_not_log_authorization_header(caplog):
    """Authorization values must never appear in access log output."""
    scope = _make_scope()
    scope["headers"] = [(b"authorization", b"Bearer super-secret-token")]
    with caplog.at_level(logging.INFO, logger="app.middleware.access_log"):
        asyncio.run(_run_middleware(scope))
    for record in caplog.records:
        assert "super-secret-token" not in record.message
        assert "Authorization" not in record.message


def test_access_log_captures_non_200_status(caplog):
    scope = _make_scope(path="/api/owned-shoes")
    with caplog.at_level(logging.INFO, logger="app.middleware.access_log"):
        asyncio.run(_run_middleware(scope, response_status=401))
    msg = caplog.records[-1].message
    assert "401" in msg


def test_access_log_skips_non_http_scopes(caplog):
    """Lifespan events (scope type != 'http') must not generate a log line."""
    async def run():
        calls = []

        async def fake_app(scope, receive, send):
            calls.append("called")

        middleware = AccessLogMiddleware(fake_app)
        await middleware({"type": "lifespan"}, None, None)
        return calls

    calls = asyncio.run(run())
    assert calls == ["called"]
    access_records = [r for r in caplog.records if r.name == "app.middleware.access_log"]
    assert len(access_records) == 0
