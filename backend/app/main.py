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
from app.routers import shoes, retailers, deals, dashboard, scraping, export, owned_shoes, coros_sync, chat, admin, training, strava, watchlist, activities, races, home

# Load environment variables
load_dotenv()


def require_anton_secret() -> None:
    """
    Fail fast if the R2.1 auth secret is missing.

    Auth is *not* an optional feature (contrast the graceful-degradation pattern
    for optional creds in CLAUDE.md §4.6): absence is fatal, never a silently
    unauthenticated server. Called at startup, before the app serves any request.
    The `.env.example` placeholder is an empty string, so empty/whitespace counts
    as unset. Raises RuntimeError so uvicorn aborts the boot with a clear message.
    """
    if not os.getenv("ANTON_SECRET", "").strip():
        raise RuntimeError(
            "ANTON_SECRET is not set. The API refuses to start without it "
            "(R2.1 security pass — SECURITY_PASS_PLAN.md). Generate one with: "
            'python -c "import secrets; print(secrets.token_hex(32))" '
            "and set ANTON_SECRET (and VITE_ANTON_SECRET) in backend/.env."
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
    require_anton_secret()
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
