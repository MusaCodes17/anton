"""
MCP server exposing this app's core functionality as tools, resources and prompts for LLM clients.

Mounted onto the FastAPI app (see app/main.py) at /mcp via
mcp.streamable_http_app(), using Streamable HTTP transport.

Tools stay thin on purpose: they read the same SQLAlchemy models and call
the same ScrapeOrchestrator the REST routers (app/routers/*.py) use, so there is
exactly one place business logic lives. Each tool opens its own DB session
(FastMCP tools aren't FastAPI route handlers, so they can't use
Depends(get_db)) and closes it when done, mirroring get_db's lifecycle.

Layout: _core (FastMCP instance, session helper), _shared (cross-domain helpers),
and one module per domain: deals, shoes, coros, training, onboarding. New
tools/resources/prompts go in the matching domain module and are re-exported below.
"""
from app.mcp_server._core import mcp

# Importing the domain modules (in this order) registers their tools/resources/prompts on `mcp`.
from app.mcp_server.deals import (
    get_deals,
    get_shoe_deals,
    get_watchlist,
    get_shoes,
    get_retailers,
    add_shoe,
    delete_shoe,
    scrape_health,
    trigger_scrape,
    get_dashboard_stats,
    get_price_history,
    active_deals_resource,
    deals_watchlist_resource,
    retailers_resource,
    brand_deals_resource,
    get_deal_alerts,
    deal_alert_digest,
    get_coupon_opportunities,
    hunt_coupons,
    coupon_digest,
)
from app.mcp_server.shoes import (
    get_owned_shoes,
    get_shoe_runs,
    log_run_to_shoe,
    delete_shoe_run,
    get_shoe_notes,
    add_shoe_note,
    draft_shoe_review,
    save_shoe_review,
    set_shoe_mileage_limit,
    retire_shoe,
    shoe_rotation_resource,
    shoe_detail_resource,
    shoe_runs_resource,
    shoe_notes_resource,
    shoe_review_resource,
    weekly_rotation_summary,
)
from app.mcp_server.coros import (
    get_coros_sync_status,
    sync_coros_now,
    fetch_unsynced_coros_runs,
    confirm_coros_run,
    sync_coros_runs,
)
from app.mcp_server.training import (
    get_training_summary,
    get_training_trends,
    get_personal_bests,
    record_athlete_metrics,
    get_planned_races,
    get_weekly_summary,
    strava_runs_by_month_resource,
    training_summary_resource,
    training_fitness_resource,
    sync_fitness,
    get_race_block_context,
    race_block_advisor,
)
from app.mcp_server.onboarding import (
    get_onboarding_queue,
    probe_retailer,
    onboard_retailer,
    mark_retailer_unscrapable,
    retailer_onboarding,
)

__all__ = [
    "mcp",
    "get_deals",
    "get_shoe_deals",
    "get_watchlist",
    "get_shoes",
    "get_retailers",
    "add_shoe",
    "delete_shoe",
    "scrape_health",
    "trigger_scrape",
    "get_dashboard_stats",
    "get_price_history",
    "active_deals_resource",
    "deals_watchlist_resource",
    "retailers_resource",
    "brand_deals_resource",
    "get_deal_alerts",
    "deal_alert_digest",
    "get_coupon_opportunities",
    "hunt_coupons",
    "coupon_digest",
    "get_owned_shoes",
    "get_shoe_runs",
    "log_run_to_shoe",
    "delete_shoe_run",
    "get_shoe_notes",
    "add_shoe_note",
    "draft_shoe_review",
    "save_shoe_review",
    "set_shoe_mileage_limit",
    "retire_shoe",
    "shoe_rotation_resource",
    "shoe_detail_resource",
    "shoe_runs_resource",
    "shoe_notes_resource",
    "shoe_review_resource",
    "weekly_rotation_summary",
    "get_coros_sync_status",
    "sync_coros_now",
    "fetch_unsynced_coros_runs",
    "confirm_coros_run",
    "sync_coros_runs",
    "get_training_summary",
    "get_training_trends",
    "get_personal_bests",
    "record_athlete_metrics",
    "get_planned_races",
    "get_weekly_summary",
    "strava_runs_by_month_resource",
    "training_summary_resource",
    "training_fitness_resource",
    "sync_fitness",
    "get_race_block_context",
    "race_block_advisor",
    "get_onboarding_queue",
    "probe_retailer",
    "onboard_retailer",
    "mark_retailer_unscrapable",
    "retailer_onboarding",
]
