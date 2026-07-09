"""
Bearer-token auth middleware (RA1.1 — per-client named tokens + capability-URL).

Anton's auth model is now per-client and individually revocable. Two mechanisms:

1. **Named bearer tokens** (`ANTON_TOKENS="name:token,name:token,..."`) — every
   REST API and MCP bearer client (desktop, spa, loopback) gets its own token.
   Revoking one client means removing its entry and restarting; the others keep
   working. The presented `Authorization: Bearer <token>` is compared against the
   full token set using constant-time comparison without short-circuiting.

2. **Capability-URL** (`ANTON_CONNECTOR_TOKEN=<long-hex>`) — the claude.ai mobile
   connector cannot send custom headers; the URL itself is the credential. Requests
   to `/mcp/<CONNECTOR_TOKEN>/...` are authenticated by the URL token, and the
   middleware rewrites the path to `/mcp/...` before forwarding to the FastMCP
   mount. **Explicitly interim** (recorded in design_decisions.md) — upgrade to
   OAuth 2.1 later if needed; capability-URL is acceptable only layered with TLS,
   auth-failure logging, and rate limiting (RA1.3).

Why a *pure ASGI* middleware and not `BaseHTTPMiddleware` or a dependency:
- The app streams SSE (chat + scrape progress) and serves the `/mcp` Streamable
  HTTP transport. `BaseHTTPMiddleware` wraps/buffers the response body and is a
  known breaker of streaming responses — this middleware only inspects the request
  headers and forwards `receive`/`send` untouched, so streams pass through intact.
- A middleware (not a per-router dependency) covers *every* route, including the
  mounted `/mcp` sub-app, without per-router decoration.

Registered *inside* CORS in `main.py` (added before `CORSMiddleware`, so CORS is
the outer wrapper) so that a 401 response still carries CORS headers and the
browser surfaces a clean 401 instead of an opaque CORS error.

Supersedes R2.1's single-secret `BearerAuthMiddleware` (design_decisions E7 → E9).
"""
from __future__ import annotations

import os
import secrets

# Paths reachable without a token: the root banner and the liveness probes. These
# leak nothing sensitive and must stay open (a monitor/health check has no token).
PUBLIC_PATHS: frozenset[str] = frozenset({"/", "/health", "/api/health"})

_BEARER_PREFIX = "bearer "  # case-insensitive scheme match


def _parse_token_map(env_val: str) -> dict[str, str]:
    """
    Parse 'name:token,name:token,...' into {name: token}.

    Uses partition(':') so tokens can't contain ',' but may contain ':'. Skips
    malformed entries (missing name or empty token) silently.
    """
    tokens: dict[str, str] = {}
    for pair in env_val.split(","):
        pair = pair.strip()
        if not pair:
            continue
        name, sep, token = pair.partition(":")
        name = name.strip()
        token = token.strip()
        if sep and name and token:
            tokens[name] = token
    return tokens


def get_named_token(name: str) -> str:
    """
    Return the token for a named client from `ANTON_TOKENS`.

    Read from the environment on each call (not cached) so internal callers —
    e.g. chat_service's loopback — always see the live value, even if the env
    was populated after module import. Returns '' if the name is not in the map.
    """
    return _parse_token_map(os.getenv("ANTON_TOKENS", "")).get(name, "")


class BearerAuthMiddleware:
    """
    Pure ASGI middleware enforcing per-client named bearer tokens (RA1.1).

    Reads `ANTON_TOKENS` and `ANTON_CONNECTOR_TOKEN` once at construction
    (Starlette builds the middleware stack once at startup). An empty token set
    denies *everything* — belt-and-braces behind `main.require_auth_config()`'s
    fail-fast, so a misconfigured server can never accidentally authorize.
    """

    def __init__(self, app):
        self.app = app
        self.tokens: dict[str, str] = _parse_token_map(
            os.getenv("ANTON_TOKENS", "")
        )
        self.connector_token: str = os.getenv("ANTON_CONNECTOR_TOKEN", "").strip()

    async def __call__(self, scope, receive, send):
        # Non-HTTP scopes (lifespan, websockets if ever added) pass through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # CORS preflight must never require the token, or the browser preflight
        # breaks. (Starlette's CORSMiddleware already answers real preflights
        # before us; this is defence for any OPTIONS that slips through.)
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if scope.get("path") in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        # Capability-URL: /mcp/<CONNECTOR_TOKEN>/... is authenticated by the URL.
        # Rewrite the path to /mcp/... so the FastMCP mount (at /mcp) sees a
        # normal request. The URL token never appears in the forwarded path.
        if self.connector_token:
            cap_prefix = f"/mcp/{self.connector_token}"
            path = scope.get("path", "")
            if path == cap_prefix or path.startswith(cap_prefix + "/"):
                new_path = "/mcp" + path[len(cap_prefix):]
                new_scope = dict(scope)
                new_scope["path"] = new_path
                new_scope["raw_path"] = new_path.encode("latin-1")
                await self.app(new_scope, receive, send)
                return

        if self._authorized(scope):
            await self.app(scope, receive, send)
            return

        await self._reject(send)

    def _authorized(self, scope) -> bool:
        if not self.tokens:
            return False
        header = self._get_header(scope, b"authorization")
        if not header or not header.lower().startswith(_BEARER_PREFIX):
            return False
        presented = header[len(_BEARER_PREFIX):].strip()
        # Compare against every token without short-circuiting so a timing
        # side-channel can't reveal which token matched or how many exist.
        result = False
        for token in self.tokens.values():
            result |= secrets.compare_digest(presented, token)
        return result

    @staticmethod
    def _get_header(scope, name: bytes) -> str | None:
        for key, value in scope.get("headers", []):
            if key == name:
                return value.decode("latin-1")
        return None

    @staticmethod
    async def _reject(send) -> None:
        # 401 with an empty body — no `WWW-Authenticate`, no reason string.
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-length", b"0")],
            }
        )
        await send({"type": "http.response.body", "body": b""})
