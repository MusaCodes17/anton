"""
Main FastAPI application
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

from app.database import run_migrations
from app.mcp_server import mcp
from app.middleware.auth import BearerAuthMiddleware
from app.routers import shoes, retailers, deals, dashboard, scraping, export, owned_shoes, coros_sync, chat, admin, training, strava, watchlist, activities, races, home, shoe_types, checkpoints, oauth as oauth_router

# Load environment variables
load_dotenv()


def require_auth_config() -> None:
    """
    Fail fast if no auth credentials are configured (RA1.1).

    Auth is *not* an optional feature: absence is fatal, never a silently
    unauthenticated server. `ANTON_TOKENS` must be non-empty. An empty-but-present
    env var is treated as unset. Raises RuntimeError so uvicorn aborts with a
    clear message.

    Note: `ANTON_CONNECTOR_TOKEN` (capability-URL) was removed in RA1.1b when
    OAuth 2.1 replaced it (design_decisions E9). Do not re-add that fallback.
    """
    tokens = os.getenv("ANTON_TOKENS", "").strip()
    if not tokens:
        raise RuntimeError(
            "No auth credentials configured. Set ANTON_TOKENS (RA1.1) in backend/.env. "
            "Example: ANTON_TOKENS=\"desktop:$(python3 -c 'import secrets; print(secrets.token_hex(32))')\""
            ",loopback:$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
            ",spa:$(python3 -c 'import secrets; print(secrets.token_hex(32))')\""
            " — see REMOTE_ACCESS_PLAN.md §6 RA1.1."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Validate the auth secret, upgrade the DB to Alembic head (R2.2 — the sole
    schema authority), then run the MCP server's session manager for the lifetime
    of the app. Streamable HTTP transport needs that session manager's task group
    active — mounting mcp.streamable_http_app() alone doesn't run a sub-app's
    lifespan, so it's merged in here instead.
    """
    require_auth_config()
    run_migrations()
    print("✅ Database migrated to head")
    async with mcp.session_manager.run():
        yield


# Create FastAPI app
app = FastAPI(
    title="Running Shoe Deal Finder",
    description="API for finding deals on running shoes from Canadian retailers",
    version="1.0.0",
    lifespan=lifespan,
)

# Bearer-token auth (R2.1). Added BEFORE CORS so that CORS is the *outer* wrapper
# (Starlette's add_middleware makes the last-added middleware outermost): a 401
# from auth then still gets CORS headers, so the browser surfaces a clean 401
# rather than an opaque CORS error. See app/middleware/auth.py.
app.add_middleware(BearerAuthMiddleware)

# Configure CORS
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(shoes.router, prefix="/api")
app.include_router(retailers.router, prefix="/api")
app.include_router(deals.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(scraping.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(coros_sync.router, prefix="/api")
app.include_router(owned_shoes.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(training.router, prefix="/api")
app.include_router(strava.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(activities.router, prefix="/api")
app.include_router(races.router, prefix="/api")
app.include_router(home.router, prefix="/api")
app.include_router(shoe_types.router, prefix="/api")
app.include_router(checkpoints.router, prefix="/api")

# OAuth 2.1 login page — always registered (needed even when OAuth is not
# fully configured so the route exists for graceful "not configured" handling).
app.include_router(oauth_router.router)

# OAuth 2.1 protocol routes (/.well-known, /authorize, /token, /revoke).
# Registered only when ANTON_HOST_URL is set — that var is the issuer URL and
# its presence signals that the OAuth server should be active.
_host_url = os.getenv("ANTON_HOST_URL", "").strip()
if _host_url:
    from mcp.server.auth.routes import create_auth_routes
    from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
    from pydantic import AnyHttpUrl
    from app.services.oauth import get_provider as _get_oauth_provider

    _oauth_routes = create_auth_routes(
        _get_oauth_provider(),
        issuer_url=AnyHttpUrl(_host_url),
        client_registration_options=ClientRegistrationOptions(enabled=False),
        revocation_options=RevocationOptions(enabled=True),
    )
    app.router.routes.extend(_oauth_routes)

# Mount the MCP server (Streamable HTTP transport) at /mcp
app.mount("/mcp", mcp.streamable_http_app())


# Root endpoint
@app.get("/")
def read_root():
    """Root endpoint - API information"""
    return {
        "message": "Running Shoe Deal Finder API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running"
    }


# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# API-namespaced liveness alias — exempt from auth (see app/middleware/auth.py
# PUBLIC_PATHS) so a monitor or the SPA can probe liveness without the token.
@app.get("/api/health")
def api_health_check():
    """Liveness probe under the /api prefix. Public (no token required)."""
    return {"status": "healthy"}


# To run this application, use: python run.py from the backend directory
# Or use: uvicorn app.main:app --reload
