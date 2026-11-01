"""Helpers shared across the MCP domain modules (dict projections + text formatters).

Private to the package: tools/resources import these by name; nothing here is registered with FastMCP.
"""
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import Deal, OwnedShoe, PriceRecord, Shoe, ShoeNote, ShoeRun
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


def _deal_brief(deal: Deal) -> dict:
    """LLM projection of a deal (R14 T5c); the REST schema is the full record.

    Sits beside `_deal_to_dict`, which stays the full flat projection for `detail=True`.
    `id` is the value draft_purchase_from_deal takes. Drops msrp, target_price,
    savings_amount, in_stock, sizes_available, colorway, shoe_type and detected_at.
    """
    return {
        "id": deal.id,
        "shoe_id": deal.shoe_id,
        "shoe": f"{deal.shoe.brand} {deal.shoe.model}",
        "retailer": deal.retailer.name,
        "price": deal.current_price,
        "savings_percent": deal.savings_percent,
        "size_fit": getattr(deal, "size_fit", None),  # same rule as _deal_to_dict
        "url": deal.product_url,
    }


def _watchlist_entry_payload(entry) -> dict:
    """Watchlist row via the REST schema (`WatchlistItem`) so MCP and REST can't drift."""
    return WatchlistItem.model_validate(entry).model_dump(mode="json")


def _watchlist_brief(entry) -> dict:
    """LLM projection of a watchlist entry (R14 T5a); the REST schema is the full record.

    Drops image_url, best_ever_at, last_seen and the other best_deal fields: the
    per-retailer last-seen list is what made get_watchlist ~24k tokens. Reads the
    service dataclass attributes directly (`watchlist_svc.build_watchlist`) and runs no query.
    """
    deal = entry.best_deal
    return {
        "shoe_id": entry.shoe_id,
        "brand": entry.brand,
        "model": entry.model,
        "shoe_type": entry.shoe_type,
        "msrp": entry.msrp,
        "target_price": entry.target_price,
        "on_sale": entry.on_sale,
        "best_deal": None if deal is None else {
            "deal_id": deal.deal_id,
            "retailer_name": deal.retailer_name,
            "current_price": deal.current_price,
            "savings_percent": deal.savings_percent,
        },
        "best_ever_price": entry.best_ever_price,
    }


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


def _pct_of_limit(current_km: float, limit_km: Optional[float]) -> Optional[int]:
    """Whole-percent mileage against the retirement limit; None when there is no limit.

    Shared by the shoe resource and the LLM brief so the two can't round differently.
    """
    return round(current_km / limit_km * 100) if limit_km else None


def _owned_shoe_brief(shoe: OwnedShoe) -> dict:
    """LLM projection of an owned shoe (R14 T1); the REST schema is the full record.

    Reads `shoe.total_runs`, which `rotation.attach_computed_fields_bulk` sets, so the
    caller must attach first. Runs no query.
    """
    label = shoe.nickname or ""
    return {
        "id": shoe.id,
        "name": f"{shoe.brand} {shoe.model}" + (f" ({label})" if label else ""),
        "shoe_type": shoe.shoe_type,
        "status": shoe.status,
        "current_mileage_km": round(shoe.current_mileage, 1),
        "mileage_limit_km": shoe.mileage_limit,
        "pct_of_limit": _pct_of_limit(shoe.current_mileage, shoe.mileage_limit),
        "total_runs": shoe.total_runs,
    }


def _shoe_run_brief(run: ShoeRun) -> dict:
    """LLM projection of an attributed run (R14 T1); the REST schema is the full record.

    `run_id` is the ShoeRun id (what delete_shoe_run takes). The caller eager-loads
    `ShoeRun.activity`.
    """
    a = run.activity
    return {
        "run_id": run.id,
        "date": a.run_date.isoformat(),
        "distance_km": a.distance_km,
        "avg_pace": rotation.seconds_to_pace(a.avg_pace_s_per_km) if a.avg_pace_s_per_km is not None else None,
        "avg_hr": a.avg_hr,
        "activity_tag": a.activity_tag,
        "source": a.source,
    }


def _scrape_health_brief(health: dict) -> dict:
    """LLM projection of `scrape_history.scrape_health` (R14 T5b); the REST schema is the full record.

    Keeps each retailer's verdict, latest-run outcome, a newest-first product-count trend and
    the watchdog fields, plus the two top-level attention lists. Drops the per-run records in
    `trend` and the flat `recent_runs` log. Copies values from the service dict only and runs no query.
    """
    retailers = []
    for row in health["retailers"]:
        latest = row["latest_run"]
        retailers.append({
            "retailer_id": row["retailer_id"],
            "name": row["name"],
            "health": row["health"],
            "scraping_enabled": row["scraping_enabled"],
            "last_status": latest["status"] if latest else None,
            "last_run_at": latest["started_at"] if latest else None,
            "products_found": latest["products_found"] if latest else None,
            "error": latest["error"] if latest else None,
            "products_trend": [r["products_found"] for r in row["trend"]],
            "watchdog_alert": row["watchdog_alert"],
            "watchdog_reason": row["watchdog_reason"],
        })
    return {
        "retailers": retailers,
        "retailers_needing_attention": health["retailers_needing_attention"],
        "needs_onboarding": health["needs_onboarding"],
    }


# Coupon brief: one retailer carried 28 active deals, and `all_retailers` and `stackable`
# both repeated the full list. The brief keeps the top few by savings and reports the full
# count in `deals_total`, so a single retailer no longer dominates the payload.
_COUPON_BRIEF_DEALS = 5


def _tracked_shoe_brief(shoe: Shoe, *, include_active: bool = False) -> dict:
    """LLM projection of a tracked (watchlist) shoe for get_shoes; the full record is behind detail=True.

    `shoe` is "Brand Model" in one field, as in `_deal_brief`. Drops `notes` (the free-text
    journal that can run long), and brand and model as separate fields. `is_active` appears
    only when `include_active` is True: with the default active-only filter every row is
    active, so the flag is noise. get_shoes passes True when asked for all shoes. Copies
    columns only and runs no query.
    """
    brief = {
        "id": shoe.id,
        "shoe": f"{shoe.brand} {shoe.model}",
        "shoe_type": shoe.shoe_type,
        "msrp": shoe.msrp,
        "target_price": shoe.target_price,
    }
    if include_active:
        brief["is_active"] = shoe.is_active
    return brief


def _price_record_brief(record: PriceRecord) -> dict:
    """LLM projection of one scraped price row for get_price_history; the full row is behind detail=True.

    `date` is the calendar date of `scraped_at` (None when unset). Drops original_price, in_stock,
    colorway and the full timestamp. One row per scrape record, with no dedupe. Needs `record.retailer`.
    """
    return {
        "retailer": record.retailer.name,
        "price": record.price,
        "date": record.scraped_at.date().isoformat() if record.scraped_at else None,
    }


def _promo_code_brief(promo: dict) -> dict:
    """Brief promo code row for get_coupon_opportunities; drops `source` (the full row is behind detail=True)."""
    return {
        "code": promo["code"],
        "description": promo["description"],
        "discount_percent": promo["discount_percent"],
        "last_seen_at": promo["last_seen_at"],
    }


def _coupon_opportunities_brief(opps: dict) -> dict:
    """LLM projection of `coupon_hunter.get_stacking_opportunities` for get_coupon_opportunities.

    Pure dict transform over the service result; runs no query. Promo codes drop `source`.
    `stackable` rows keep the top `_COUPON_BRIEF_DEALS` deals by savings (None last, ties by shoe
    name) and report the full count as `deals_total`. `all_retailers` rows carry `deals_total` only.
    The full record, with every deal, is behind detail=True.
    """
    def _sort_key(deal: dict):
        savings = deal["savings_percent"]
        return (savings is None, -(savings or 0.0), deal["shoe"])

    all_retailers = [
        {
            "retailer_id": r["retailer_id"],
            "name": r["name"],
            "promo_codes": [_promo_code_brief(pc) for pc in r["promo_codes"]],
            "deals_total": len(r["deals"]),
        }
        for r in opps["all_retailers"]
    ]
    stackable = [
        {
            "retailer_id": r["retailer_id"],
            "name": r["name"],
            "promo_codes": [_promo_code_brief(pc) for pc in r["promo_codes"]],
            "deals": [dict(d) for d in sorted(r["deals"], key=_sort_key)[:_COUPON_BRIEF_DEALS]],
            "deals_total": len(r["deals"]),
        }
        for r in opps["stackable"]
    ]
    return {
        "all_retailers": all_retailers,
        "stackable": stackable,
        "total_active_codes": opps["total_active_codes"],
        "stackable_count": opps["stackable_count"],
    }


# R14 E27 briefs for get_rotation_insights and get_race_block_context. Each brief is a list
# of kept keys, so what the model sees is readable here and the dropped fields are the
# difference from the service dict. The full payloads stay behind detail=True (= REST).
_MODEL_ROW_KEYS = ("brand", "model", "runs", "km", "steady_runs", "median_m_per_beat",
                   "median_pace_s_per_km", "median_avg_hr", "enough_data")


def _rotation_insights_brief(full: dict) -> dict:
    """LLM projection of `RotationInsightsResponse.model_dump()` for get_rotation_insights.

    Pure dict transform; runs no query. Model rows drop `pair_ids` and the per-row
    `min_steady_runs`, `heuristic` and `caveat`, which were identical text on every row; the
    caveat and threshold are stated once at the top level (from the insights service constants,
    so they are present even with zero models). `wear_by_type` is unchanged.
    """
    from app.services import insights
    return {
        "models": [{k: row[k] for k in _MODEL_ROW_KEYS} for row in full["models"]],
        "wear_by_type": full["wear_by_type"],
        "caveat": insights.PERFORMANCE_CAVEAT,
        "min_steady_runs": insights.MIN_SHOE_STEADY_RUNS,
        "heuristic": True,
    }


_RACE_WEEK_KEYS = ("period", "total_km", "run_count", "avg_pace")
_RACE_PIPELINE_KEYS = ("brand", "model", "nickname", "shoe_type", "pct", "current_mileage",
                       "mileage_limit", "replacement_deals")
_READINESS_KEPT_KEYS = ("has_race", "as_of", "race", "race_class", "block_weeks", "block_start",
                        "block_end", "block_started", "block_km", "block_runs", "peak_week",
                        "current_week", "longest_run", "long_run_km", "long_runs_needed",
                        "key_effort", "race_shoe", "days_before_race", "heuristic")
_CHECKLIST_KEYS = ("key", "label", "status", "rule", "value", "target", "unit")
_PAST_BUILD_KEYS = ("result_vs_target_s", "km", "runs", "long_runs", "longest_km", "peak_week_km")
_FINISH_KEYS = ("run_date", "distance_km", "has_splits", "first_half_pace_s_per_km",
                "second_half_pace_s_per_km", "split_diff_s_per_km", "last_km_vs_avg_s_per_km",
                "second_half_vs_target_s_per_km")
_ESTIMATE_KEYS = ("state", "message", "estimate_s", "low_s", "high_s", "band_pct", "grade",
                  "grade_reasons", "target_position", "backtest_n", "coros_prediction_s",
                  "coros_captured_at", "heuristic")


def _pick(row: dict, keys: tuple) -> dict:
    return {k: row[k] for k in keys}


def _past_build_brief(build: dict) -> dict:
    race = build["race"]
    return {"race_name": race["name"], "race_date": race["race_date"], "status": race["status"],
            **_pick(build, _PAST_BUILD_KEYS)}


def _readiness_brief(readiness: Optional[dict]) -> Optional[dict]:
    """Projection of the readiness payload; None stays None. Drops long_runs, effort_window_start,
    recent_efforts, consistency and taper, and trims checklist, past_builds, long_run_finishes and
    estimate to the keys above (the checklist's info items carry the numbers the dropped objects held)."""
    if readiness is None:
        return None
    out = _pick(readiness, _READINESS_KEPT_KEYS)
    out["checklist"] = [_pick(i, _CHECKLIST_KEYS) for i in readiness["checklist"]]
    out["past_builds"] = [_past_build_brief(b) for b in readiness["past_builds"]]
    out["long_run_finishes"] = [_pick(f, _FINISH_KEYS) for f in readiness["long_run_finishes"]]
    est = readiness["estimate"]
    out["estimate"] = None if est is None else _pick(est, _ESTIMATE_KEYS)
    return out


def _race_block_brief(full: dict) -> dict:
    """LLM projection of the get_race_block_context result (R14 E27); the full result is behind detail=True.

    Pure dict transform over `full`, which it never mutates; runs no query. Keeps every top-level
    key. `recent_weeks` drops avg_hr; `pipeline` drops shoe_id and the forecast fields; `readiness`
    goes through `_readiness_brief` (None, and has_race False with no estimate, are handled).
    """
    out = dict(full)
    out["recent_weeks"] = [_pick(w, _RACE_WEEK_KEYS) for w in full["recent_weeks"]]
    out["pipeline"] = [_pick(p, _RACE_PIPELINE_KEYS) for p in full["pipeline"]]
    out["readiness"] = _readiness_brief(full["readiness"])
    return out


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
