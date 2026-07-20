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

3. **Session cookie** (`anton_session`, RA2.1) — the SPA authenticates by
   password once (`POST /api/auth/session`) and receives an httpOnly cookie. This
   middleware verifies the cookie via `services.sessions.verify_session_sync`
   after the named-bearer and OAuth checks fail. This retires the baked-in `spa`
   bearer token — the built bundle now carries no secret. Session auth is an
   *additional* credential type, not a replacement for (1) or (2).

CSRF (RA2.1) — cookies are sent automatically by the browser, so cookie-
authenticated *mutating* requests (POST/PUT/PATCH/DELETE on `/api/*`) get an
extra guard: the `Origin` header must equal `ANTON_HOST_URL` (exact compare).
SameSite=Lax on the cookie is the first line of defence; the Origin check is
defence-in-depth. Requests authenticated by (1) or (2) carry no cookie and are
exempt. GET/HEAD and SSE (EventSource is GET) are exempt.

Why a *pure ASGI* middleware and not `BaseHTTPMiddleware` or a dependency:
- The app streams SSE (chat + scrape progress) and serves the `/mcp` Streamable
  HTTP transport. `BaseHTTPMiddleware` wraps/buffers the response body and is a
  known breaker of streaming responses — this middleware only inspects the request
  headers and forwards `receive`/`send` untouched, so streams pass through intact.
- A middleware (not a per-router dependency) covers *every* route, including the
  mounted `/mcp` sub-app, without per-router decoration.

RA1.3 additions:
- Every 401 is logged at WARNING with source IP + method + path.
- Repeated 401s from the same IP are throttled via `auth_failure_limiter`
  (services/rate_limit.py): after the burst is exhausted, the response becomes
  429 rather than 401 and the Retry-After header says how long to wait.
- On successful auth the matched client name is stored in `scope["anton_client"]`
  so the AccessLogMiddleware can include it in the structured access log.

Registered *inside* CORS in `main.py` (added before `CORSMiddleware`, so CORS is
the outer wrapper) so that a 401 response still carries CORS headers and the
browser surfaces a clean 401 instead of an opaque CORS error.

Supersedes R2.1's single-secret `BearerAuthMiddleware` (design_decisions E7 → E9).
Capability-URL connector auth (RA1.1 interim) removed in RA1.1b (design_decisions E9).
"""
from __future__ import annotations

import logging
import os
import secrets

logger = logging.getLogger(__name__)

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
    # SPA session-cookie auth (RA2.1): password login, logout, and the load-time
    # probe. POST issues the cookie (can't require the cookie it's about to set);
    # GET reports {authenticated}; DELETE is a self-scoped logout — all three
    # validate internally, so the path is safe to make public.
    #
    # The SPA's static assets (index.html, JS/CSS bundle) are NOT listed here
    # because they are served by Caddy's file_server, never by this backend — the
    # backend only handles /api, /mcp, and the OAuth routes. The bundle holds no
    # secret now, so serving it publicly is correct regardless.
    "/api/auth/session",
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


def _client_ip(scope) -> str:
    """Extract the real client IP.

    Checks X-Forwarded-For first (set by Caddy in the production deployment via
    `header_up X-Forwarded-For {remote_host}`) — takes only the first IP in the
    list, which is the original client when Caddy sets exactly one value. Falls
    back to the ASGI-layer client tuple for direct connections (dev, tests).
    """
    for key, value in scope.get("headers", []):
        if key == b"x-forwarded-for":
            forwarded = value.decode("latin-1").split(",")[0].strip()
            if forwarded:
                return forwarded
    client = scope.get("client")
    return client[0] if client else "unknown"


class BearerAuthMiddleware:
    """
    Pure ASGI middleware enforcing per-client named bearer tokens (RA1.1) with
    an OAuth 2.1 access token fallback (RA1.1b) and auth-failure logging +
    rate limiting (RA1.3).

    Reads `ANTON_TOKENS` once at construction (Starlette builds the middleware
    stack once at startup). An empty token set denies *everything* — belt-and-
    braces behind `main.require_auth_config()`'s fail-fast, so a misconfigured
    server can never accidentally authorize.

    OAuth fallback: when named-token check fails and ANTON_HOST_URL is set, the
    presented Bearer token is verified against the oauth_tokens DB table via
    `services.oauth.verify_access_token_sync`.  This is a synchronous DB call
    in an async context — acceptable for single-user SQLite (sub-millisecond,
    no concurrency hazard under INV-9).

    RA1.3: successful auth stores the client name in scope["anton_client"] for
    the access log.  Failed auth logs WARNING + optionally returns 429 when the
    per-IP failure bucket is exhausted.
    """

    def __init__(self, app):
        self.app = app
        self.tokens: dict[str, str] = _parse_token_map(
            os.getenv("ANTON_TOKENS", "")
        )
        # OAuth is active when ANTON_HOST_URL is set — same condition as main.py
        # wires create_auth_routes().
        host = os.getenv("ANTON_HOST_URL", "").strip()
        self._oauth_active: bool = bool(host)
        # CSRF origin target for cookie-authenticated writes (RA2.1). Stored
        # without a trailing slash so the exact-compare matches the browser's
        # Origin header (which never has a trailing slash). Empty in dev (no
        # host URL) → CSRF enforcement is skipped and SameSite=Lax is the guard.
        self._csrf_origin: str = host.rstrip("/")
        # Imported lazily so tests can swap the singleton before this module is
        # loaded; also avoids a circular-import risk at module level.
        from app.services.rate_limit import auth_failure_limiter
        self._failure_limiter = auth_failure_limiter

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

        client = self._authorized(scope)
        if client is not None:
            # CSRF applies ONLY to cookie-authenticated writes (RA2.1). Bearer
            # and OAuth clients carry no cookie and are exempt.
            if client == "session" and not self._csrf_ok(scope):
                method = scope.get("method", "?")
                path = scope.get("path", "?")
                logger.warning("csrf reject: %s %s from %s",
                               method, path, _client_ip(scope))
                await self._reject_csrf(send)
                return
            await self.app(scope, receive, send)
            return

        # Auth failed — log and apply per-IP throttle.
        ip = _client_ip(scope)
        method = scope.get("method", "?")
        path = scope.get("path", "?")
        result = self._failure_limiter.take(ip)
        if not result.allowed:
            logger.warning("auth rate-limited: %s %s from %s", method, path, ip)
            await self._reject_rate_limited(send, result.retry_after_s)
        else:
            logger.warning("auth 401: %s %s from %s", method, path, ip)
            await self._reject(send)

    def _authorized(self, scope) -> str | None:
        """Check the presented credentials; on success set scope['anton_client']
        and return the client type ('<named>' | 'oauth' | 'session'). Returns
        None when no credential authorizes the request.

        Named-token comparison loops over ALL tokens unconditionally (no early
        exit from the loop body) so the wall-clock time of a failed check does
        not reveal how many tokens are registered or whether any matched.
        """
        header = self._get_header(scope, b"authorization")
        presented = ""
        if header and header.lower().startswith(_BEARER_PREFIX):
            presented = header[len(_BEARER_PREFIX):].strip()

        if presented:
            # Named bearer tokens — constant-time multi-token compare (no short-circuit).
            if self.tokens:
                matched_name: str | None = None
                for name, token in self.tokens.items():
                    # compare_digest is constant-time; we loop all tokens and
                    # record the last match so we never exit early.
                    if secrets.compare_digest(presented, token):
                        matched_name = name
                if matched_name is not None:
                    scope["anton_client"] = matched_name
                    return matched_name

            # OAuth 2.1 access token fallback (RA1.1b).
            if self._oauth_active:
                from app.services.oauth import verify_access_token_sync
                if verify_access_token_sync(presented):
                    scope["anton_client"] = "oauth"
                    return "oauth"

        # Session cookie (RA2.1) — the SPA's credential. Checked last so the
        # bearer/OAuth paths are unchanged for their clients.
        cookie_val = self._get_cookie(scope, "anton_session")
        if cookie_val:
            from app.services.sessions import verify_session_sync
            if verify_session_sync(cookie_val):
                scope["anton_client"] = "session"
                return "session"

        return None

    def _csrf_ok(self, scope) -> bool:
        """Origin-based CSRF guard for cookie-authenticated writes (RA2.1).

        Safe methods (GET/HEAD/OPTIONS) and non-/api paths are always allowed —
        SSE (EventSource) is a GET and rides through here untouched. For a
        mutating /api request the Origin header must exactly match ANTON_HOST_URL.
        When ANTON_HOST_URL is unset (dev) enforcement is skipped and SameSite=Lax
        on the cookie is the guard.
        """
        method = scope.get("method", "")
        if method in ("GET", "HEAD", "OPTIONS"):
            return True
        path = scope.get("path", "")
        if not path.startswith("/api/"):
            return True
        if not self._csrf_origin:
            return True  # dev / not configured — rely on SameSite=Lax
        origin = self._get_header(scope, b"origin")
        if not origin:
            # A same-origin fetch/XHR always sends Origin on unsafe methods; a
            # missing Origin on a cookie write is treated as a mismatch.
            return False
        return origin.rstrip("/") == self._csrf_origin

    @staticmethod
    def _get_header(scope, name: bytes) -> str | None:
        for key, value in scope.get("headers", []):
            if key == name:
                return value.decode("latin-1")
        return None

    @staticmethod
    def _get_cookie(scope, name: str) -> str | None:
        """Read one cookie value from the Cookie header, or None if absent."""
        header = BearerAuthMiddleware._get_header(scope, b"cookie")
        if not header:
            return None
        for pair in header.split(";"):
            key, sep, value = pair.strip().partition("=")
            if sep and key == name:
                return value.strip()
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

    @staticmethod
    async def _reject_csrf(send) -> None:
        # 403 for a cookie-authenticated write whose Origin doesn't match the
        # configured host (RA2.1 CSRF guard). Distinct from 401 (unauthenticated)
        # so the SPA knows the session is valid but the request was refused.
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-length", b"0")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    @staticmethod
    async def _reject_rate_limited(send, retry_after_s: float) -> None:
        retry = str(max(1, int(retry_after_s))).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-length", b"0"),
                    (b"retry-after", retry),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})
