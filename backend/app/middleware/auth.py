"""
Bearer-token auth middleware (RA1.1b — named tokens + OAuth 2.1).

Anton's auth model:

1. **Named bearer tokens** (`ANTON_TOKENS="name:token,name:token,..."`) — every
   REST API and MCP bearer client (desktop, spa, loopback) gets its own token.
   Revoking one client means removing its entry and restarting; the others keep
   working. The presented `Authorization: Bearer <token>` is compared against the
   full token set using constant-time comparison without short-circuiting.

2. **OAuth 2.1 access tokens** — the claude.ai mobile connector authenticates
   via the standard OAuth 2.1 authorization-code + PKCE flow (RA1.1b). After the
   user completes the browser login, the connector holds a short-lived access
   token. This middleware verifies those tokens by DB lookup via
   `services.oauth.verify_access_token_sync` — only when named-token check fails
   and `ANTON_HOST_URL` is set (OAuth is active).

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
Capability-URL connector auth (RA1.1 interim) removed in RA1.1b (design_decisions E9).
"""
from __future__ import annotations

import os
import secrets

# Paths reachable without a token: liveness probes, OAuth protocol endpoints, and
# the login page.  These must be public so the OAuth flow can complete without a
# pre-existing token.
PUBLIC_PATHS: frozenset[str] = frozenset({
    "/",
    "/health",
    "/api/health",
    # OAuth 2.1 protocol endpoints (created by mcp.server.auth.routes).
    "/.well-known/oauth-authorization-server",
    "/authorize",
    "/token",
    "/revoke",
    # Human-facing login page (app/routers/oauth.py).
    "/oauth/login",
})

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
    Pure ASGI middleware enforcing per-client named bearer tokens (RA1.1) with
    an OAuth 2.1 access token fallback (RA1.1b).

    Reads `ANTON_TOKENS` once at construction (Starlette builds the middleware
    stack once at startup). An empty token set denies *everything* — belt-and-
    braces behind `main.require_auth_config()`'s fail-fast, so a misconfigured
    server can never accidentally authorize.

    OAuth fallback: when named-token check fails and ANTON_HOST_URL is set, the
    presented Bearer token is verified against the oauth_tokens DB table via
    `services.oauth.verify_access_token_sync`.  This is a synchronous DB call
    in an async context — acceptable for single-user SQLite (sub-millisecond,
    no concurrency hazard under INV-9).
    """

    def __init__(self, app):
        self.app = app
        self.tokens: dict[str, str] = _parse_token_map(
            os.getenv("ANTON_TOKENS", "")
        )
        # OAuth is active when ANTON_HOST_URL is set — same condition as main.py
        # wires create_auth_routes().
        self._oauth_active: bool = bool(os.getenv("ANTON_HOST_URL", "").strip())

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

        if self._authorized(scope):
            await self.app(scope, receive, send)
            return

        await self._reject(send)

    def _authorized(self, scope) -> bool:
        header = self._get_header(scope, b"authorization")
        if not header or not header.lower().startswith(_BEARER_PREFIX):
            return False
        presented = header[len(_BEARER_PREFIX):].strip()

        # Named bearer tokens — constant-time multi-token compare (no short-circuit).
        if self.tokens:
            result = False
            for token in self.tokens.values():
                result |= secrets.compare_digest(presented, token)
            if result:
                return True

        # OAuth 2.1 access token fallback (RA1.1b).
        if self._oauth_active:
            from app.services.oauth import verify_access_token_sync
            return verify_access_token_sync(presented)

        return False

    @staticmethod
    def _get_header(scope, name: bytes) -> str | None:
        for key, value in scope.get("headers", []):
            if key == name:
                return value.decode("latin-1")
        return None

    @staticmethod
    async def _reject(send) -> None:
        # 401 with WWW-Authenticate per RFC 6750 §3.1 — tells clients they
        # need a Bearer token.  The realm hint matches the issuer for OAuth
        # clients that use it for discovery.
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-length", b"0"),
                    (b"www-authenticate", b'Bearer realm="Anton"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})
