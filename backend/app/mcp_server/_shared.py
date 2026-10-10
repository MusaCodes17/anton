"""Helpers shared across the MCP domain modules (dict projections + text formatters).

Private to the package: tools/resources import these by name; nothing here is registered with FastMCP.
"""
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import Deal, OwnedShoe, ShoeNote, ShoeRun
from app.models.schemas import OwnedShoeResponse, ShoeNoteResponse, ShoeRunResponse, WatchlistItem
from app.services import rotation


def _deal_to_dict(deal: Deal) -> dict:
    """Deliberately hand-written flat projection (brand/model/retailer name inline) for LLM
    consumers; `DealResponse` nests the full shoe and retailer objects instead. Not a drift
    bug: when adding a deal field, add it here AND to `DealResponse`."""
    return {
        "id": deal.id,
        "shoe_id": deal.shoe_id,
        "brand": deal.shoe.brand,
        "model": deal.shoe.model,
        "shoe_type": deal.shoe.shoe_type,
        "retailer": deal.retailer.name,
        "current_price": deal.current_price,
        "msrp": deal.shoe.msrp,
        "target_price": deal.target_price,
        "savings_amount": deal.savings_amount,
        "savings_percent": deal.savings_percent,
        "in_stock": deal.in_stock,
        "sizes_available": deal.sizes_available,
        "size_fit": getattr(deal, "size_fit", None),  # R6.3: in|out|unknown, None = no size set
        "colorway": deal.colorway,
        "product_url": deal.product_url,
        "detected_at": deal.detected_at.isoformat() if deal.detected_at else None,
    }


def _watchlist_entry_payload(entry) -> dict:
    """Watchlist row via the REST schema (`WatchlistItem`) so MCP and REST can't drift."""
    return WatchlistItem.model_validate(entry).model_dump(mode="json")


def _owned_shoe_payload(db: Session, shoe: OwnedShoe) -> dict:
    """Owned shoe via `OwnedShoeResponse` after `rotation.attach_computed_fields` (same as REST)."""
    return OwnedShoeResponse.model_validate(rotation.attach_computed_fields(db, shoe)).model_dump(mode="json")


def _owned_shoes_payload(db: Session, shoes: list[OwnedShoe]) -> list[dict]:
    """List form of `_owned_shoe_payload` using the bulk attach (constant query count)."""
    rotation.attach_computed_fields_bulk(db, shoes)
    return [OwnedShoeResponse.model_validate(s).model_dump(mode="json") for s in shoes]


def _shoe_note_payload(note: ShoeNote) -> dict:
    """Journal entry via `ShoeNoteResponse`."""
    return ShoeNoteResponse.model_validate(note).model_dump(mode="json")


def _shoe_run_payload(run: ShoeRun) -> dict:
    """Attribution row via `ShoeRunResponse`, projected by `rotation.shoe_run_payload`
    from the joined Activity, so callers that loop should eager-load `ShoeRun.activity`."""
    return ShoeRunResponse.model_validate(rotation.shoe_run_payload(run)).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Formatting helpers (private — used only by resource functions below)
# ---------------------------------------------------------------------------

def _format_mileage_bar(current: float, limit: Optional[float]) -> str:
    """Return a 10-block progress bar with percentage, e.g. '████████░░ 83%'."""
    if not limit or limit <= 0:
        return f"{round(current)}km"
    pct = min(current / limit, 1.0)
    filled = round(pct * 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"{bar} {round(pct * 100)}%"


def _format_relative_time(dt: Optional[datetime]) -> str:
    """Return a human-readable relative time string, e.g. '2 hours ago'."""
    if dt is None:
        return "never"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return "just now"
    if total_seconds < 3600:
        mins = total_seconds // 60
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    if total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = total_seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


# Run-source badges for the run-history resource. Default (manual) covers any
# unrecognized source.
_SOURCE_BADGES = {
    "coros": "🤖 coros",
    "strava": "🟠 strava",
    "manual": "✍ manual",
}
