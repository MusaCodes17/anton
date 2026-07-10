"""
Structured access log middleware (RA1.3).

Logs one line per HTTP request:
    {METHOD} {path} [{client}] → {status} {duration_ms:.0f}ms

"client" is set by BearerAuthMiddleware when a named token is recognized
(scope["anton_client"]).  Public paths (e.g. /health) and OAuth flows have no
token, so they log as "anon".

Credential redaction: certain query-string parameters that could carry
credential material are replaced with "***" before the path is logged.
Redacted params: code, state, access_token, token, refresh_token.
No request headers are ever logged — the Authorization header in particular
must never appear in any log line (RA1.3 hard requirement).

This middleware wraps the response using a non-buffering send wrapper: it
intercepts `http.response.start` to capture the status code, then forwards all
messages immediately so SSE, MCP streaming, and other unbuffered transports are
unaffected.

Registration order in main.py: added LAST so it is the outermost middleware,
wrapping CORS and auth — it therefore sees the final status code (including 401s
from auth and 200s with CORS headers) and measures the total request latency.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# Query-string parameter names whose values are redacted before logging.
# These appear in OAuth flows (auth codes, tokens) and must never land in logs.
_REDACT_PARAMS: frozenset[str] = frozenset({
    "code", "state", "access_token", "token", "refresh_token",
})


def _redact_query(path: str, qs: str) -> str:
    """Return path + query string with sensitive param values replaced by ***.

    Only rewrites the value portion; the key name is kept so log analysis can
    identify which param was present without exposing the credential.
    """
    if not qs:
        return path
    parts: list[str] = []
    for param in qs.split("&"):
        key, _, val = param.partition("=")
        if key.lower() in _REDACT_PARAMS and val:
            parts.append(f"{key}=***")
        else:
            parts.append(param)
    return f"{path}?{'&'.join(parts)}"


class AccessLogMiddleware:
    """Non-buffering pure-ASGI middleware that writes one structured log line
    per HTTP request after the response starts."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code = 0

        async def capture_send(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        await self.app(scope, receive, capture_send)

        duration_ms = (time.monotonic() - start) * 1000
        method = scope.get("method", "?")
        path = scope.get("path", "?")
        qs_bytes = scope.get("query_string", b"")
        qs = qs_bytes.decode("latin-1") if qs_bytes else ""
        full_path = _redact_query(path, qs)
        client = scope.get("anton_client", "anon")

        logger.info("%s %s [%s] → %d %.0fms", method, full_path, client, status_code, duration_ms)
