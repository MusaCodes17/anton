"""Helpers shared across the MCP domain modules (dict projections + text formatters).

Private to the package: tools/resources import these by name; nothing here is registered with FastMCP.
"""
from typing import Optional
from datetime import datetime, timezone

from app.models.models import Deal, OwnedShoe, ShoeNote, ShoeRun
from app.utils.shoe_types import default_mileage_limit
from app.services import rotation


def _deal_to_dict(deal: Deal) -> dict:
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


def _watchlist_entry_to_dict(entry) -> dict:
    return {
        "shoe_id": entry.shoe_id,
        "brand": entry.brand,
        "model": entry.model,
        "shoe_type": entry.shoe_type,
        "msrp": entry.msrp,
        "target_price": entry.target_price,
        "image_url": entry.image_url,
        "on_sale": entry.on_sale,
        "best_deal": (
            {
                "deal_id": entry.best_deal.deal_id,
                "retailer_name": entry.best_deal.retailer_name,
                "current_price": entry.best_deal.current_price,
                "savings_percent": entry.best_deal.savings_percent,
                "savings_amount": entry.best_deal.savings_amount,
                "product_url": entry.best_deal.product_url,
                "in_stock": entry.best_deal.in_stock,
            }
            if entry.best_deal else None
        ),
        "best_ever_price": entry.best_ever_price,
        "best_ever_at": entry.best_ever_at.isoformat() if entry.best_ever_at else None,
        "last_seen": [
            {
                "retailer_name": ls.retailer_name,
                "price": ls.price,
                "in_stock": ls.in_stock,
                "product_url": ls.product_url,
                "scraped_at": ls.scraped_at.isoformat() if ls.scraped_at else None,
            }
            for ls in entry.last_seen
        ],
    }


def _owned_shoe_to_dict(shoe: OwnedShoe, lifetime_stats=None) -> dict:
    pace = lifetime_stats.lifetime_avg_pace if lifetime_stats else None
    hr = lifetime_stats.lifetime_avg_hr if lifetime_stats else None
    total = lifetime_stats.total_runs if lifetime_stats else 0
    return {
        "id": shoe.id,
        "brand": shoe.brand,
        "model": shoe.model,
        "nickname": shoe.nickname,
        "shoe_type": shoe.shoe_type,
        "purchase_date": shoe.purchase_date.isoformat() if shoe.purchase_date else None,
        "starting_mileage": shoe.starting_mileage,
        "current_mileage": shoe.current_mileage,
        "status": shoe.status,
        "purchase_price": shoe.purchase_price,
        "mileage_limit": shoe.mileage_limit,
        "recommended_limit_km": default_mileage_limit(shoe.shoe_type),
        "cost_per_km": rotation.cost_per_km(shoe),
        "lifetime_avg_pace": pace,
        "lifetime_avg_hr": hr,
        "total_runs": total,
    }


def _shoe_note_to_dict(note: ShoeNote) -> dict:
    return {
        "id": note.id,
        "owned_shoe_id": note.owned_shoe_id,
        "body": note.body,
        "mileage_at_note": note.mileage_at_note,
        "triggered_by": note.triggered_by,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }


def _shoe_run_to_dict(run: ShoeRun) -> dict:
    """Flatten an attribution row + its canonical activity into the run shape
    the tools have always returned (run fields now live on the activity)."""
    a = run.activity
    return {
        "id": run.id,
        "owned_shoe_id": run.owned_shoe_id,
        "distance_km": a.distance_km if a else None,
        "run_date": a.run_date.isoformat() if a and a.run_date else None,
        "source": a.source if a else None,
        "avg_pace": rotation.seconds_to_pace(a.avg_pace_s_per_km) if a and a.avg_pace_s_per_km else None,
        "avg_hr": a.avg_hr if a else None,
        "notes": a.description if a else None,
    }


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
