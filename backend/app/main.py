"""
Main FastAPI application
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

from app.database import init_db
from app.mcp_server import mcp
from app.routers import shoes, retailers, deals, dashboard, scraping, export, owned_shoes, coros_sync, chat, admin, training, strava, watchlist, activities, races

# Load environment variables
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize the database, then run the MCP server's session manager for
    the lifetime of the app. Streamable HTTP transport needs that session
    manager's task group active — mounting mcp.streamable_http_app() alone
    doesn't run a sub-app's lifespan, so it's merged in here instead.
    """
    init_db()
    print("✅ Database initialized")
    async with mcp.session_manager.run():
        yield


# Create FastAPI app
app = FastAPI(
    title="Running Shoe Deal Finder",
    description="API for finding deals on running shoes from Canadian retailers",
    version="1.0.0",
    lifespan=lifespan,
)

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


# To run this application, use: python run.py from the backend directory
# Or use: uvicorn app.main:app --reload
