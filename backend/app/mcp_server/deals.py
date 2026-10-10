"""Deal-watching MCP surface: deals, watchlist, retailers, scraping, price history, coupons."""
from dataclasses import asdict
from typing import List, Optional
from datetime import datetime

from mcp.server.fastmcp import Context
from sqlalchemy import desc, func
from app.models.models import Deal, PriceRecord, Retailer, Shoe
from app.scrapers.orchestrator import ScrapeOrchestrator
from app.scrapers.lock import ScrapeInProgressError, scrape_guard
from app.services import settings as settings_svc, scrape_history as scrape_history_svc, deals as deals_svc, watchlist as watchlist_svc, deal_alerts as deal_alerts_svc, coupon_hunter as coupon_hunter_svc, purchase_draft as purchase_draft_svc
from app.models.schemas import PurchaseDraftResponse
from app.mcp_server import _core
from app.mcp_server._core import mcp
from app.mcp_server._shared import _deal_to_dict, _format_relative_time, _watchlist_entry_payload


@mcp.tool()
def get_deals(
    min_savings_percent: Optional[float] = None,
    brand: Optional[str] = None,
    size: Optional[str] = None,
    shoe_type: Optional[str] = None,
    limit: int = 20,
) -> List[dict]:
    """
    List active running shoe deals, biggest discount first.

    Use this for questions like "what deals are there right now", "find me
    a deal on Adidas", or "what's on sale in size 10.5". Only returns deals
    that are genuinely marked down (not just shoes sitting at full price
    that happen to be at or below target) and currently active.

    Args:
        min_savings_percent: Only include deals discounted by at least this
            percent (0-100).
        brand: Filter to a specific shoe brand (case-insensitive substring
            match), e.g. "Adidas".
        size: Filter to deals with this US size currently in stock,
            e.g. "10.5". Matched numerically, so "9" also finds "9.0" and "9 / 10.5".
        shoe_type: Filter by shoe category, e.g. "long_distance_racer",
            "daily_trainer", "tempo", "trail", "recovery", "intervals",
            "short_distance_racer".
        limit: Max number of deals to return (default 20, capped at 100).

    Each deal carries size_fit ("in" | "out" | "unknown") against the runner's
    saved shoe size; null means no size is saved. Prefer "in" deals when
    recommending, and say so when a deal's sizes are unknown.
    """
    limit = max(1, min(limit, 100))
    with _core.get_session() as db:
        deals = deals_svc.list_deals(
            db,
            min_savings_percent=min_savings_percent,
            brand=brand,
            shoe_type=shoe_type,
            size=size,
            limit=limit,
        )
        return [_deal_to_dict(d) for d in deals]


@mcp.tool()
def get_shoe_deals(brand: str, model: str) -> List[dict]:
    """
    Find all active deals for a specific shoe model, sorted by biggest
    discount first. Use this when the user asks "are there any deals on
    my Adios Pro 4?" or "what's the best price on the Vaporfly 3 right now?".

    Args:
        brand: Shoe brand, e.g. "Adidas" (case-insensitive substring match).
        model: Shoe model, e.g. "Adizero Adios Pro 4" (case-insensitive substring match).
    """
    with _core.get_session() as db:
        deals = deals_svc.list_deals(db, brand=brand, model=model)
        return [_deal_to_dict(d) for d in deals]


@mcp.tool()
def draft_purchase_from_deal(deal_id: int) -> dict:
    """
    Draft an owned-shoe record from a deal, for when the runner says they bought
    a shoe they saw on sale ("I bought the Adios from that deal").

    This only DRAFTS: it writes nothing and links nothing. It returns the fields
    to prefill the add-shoe form: brand, model, shoe_type (only if it is a known
    owned-shoe type, otherwise null), purchase_price (the deal's current price),
    purchase_date (today, Toronto), purchase_retailer, purchase_url, image_url,
    colorway, plus deal_id and deal_active (false if the deal has expired, which
    is fine: the runner may have bought it before then).

    Before saving, the runner must review the price: coupons, size pricing or an
    in-store purchase often change what was actually paid. Saving is a separate
    step the runner does in the app (the owned-shoe create form, POST
    /api/owned-shoes/). There is no MCP tool that creates an owned shoe, and
    add_shoe is NOT the right tool here: it only adds a watchlist shoe.

    Args:
        deal_id: The deal's id, as returned by get_deals or get_shoe_deals.

    Returns the draft dict on success, or {"error": "..."} if the deal does not exist.
    """
    with _core.get_session() as db:
        try:
            draft = purchase_draft_svc.purchase_draft_from_deal(db, deal_id)
        except LookupError as exc:
            return {"error": str(exc)}
        return PurchaseDraftResponse(**asdict(draft)).model_dump(mode="json")


@mcp.tool()
def get_watchlist() -> List[dict]:
    """
    List every tracked shoe with its current deal status, best-ever price,
    and last-seen prices per retailer.

    Use this to answer "what am I watching?", "what's the best price ever
    on X?", "which tracked shoes are currently on sale?", or to look up
    a shoe_id before calling trigger_scrape. On-sale shoes sort first
    (deepest discount first), then the rest alphabetically by brand/model.

    Each entry includes:
    - shoe_id, brand, model, shoe_type, msrp, target_price
    - on_sale: True if there's at least one active deal below MSRP
    - best_deal: the current lowest active deal price with savings %, or null
    - best_ever_price / best_ever_at: historical best price across all scrapes
    - last_seen: most recent scraped price per retailer (cheapest first)
    """
    with _core.get_session() as db:
        entries = watchlist_svc.build_watchlist(db)
        return [_watchlist_entry_payload(e) for e in entries]


@mcp.tool()
def get_shoes(is_active: Optional[bool] = True) -> List[dict]:
    """
    List tracked shoes and their target/retail prices.

    Use this to answer "what shoes are we tracking" or to look up a shoe's
    ID before calling another tool that needs one.

    Args:
        is_active: Filter by whether the shoe is actively monitored.
            Defaults to True (only actively-tracked shoes). Pass None for all.
    """
    with _core.get_session() as db:
        query = db.query(Shoe)
        if is_active is not None:
            query = query.filter(Shoe.is_active == is_active)
        shoes = query.order_by(Shoe.brand, Shoe.model).all()
        return [
            {
                "id": s.id,
                "brand": s.brand,
                "model": s.model,
                "shoe_type": s.shoe_type,
                "target_price": s.target_price,
                "msrp": s.msrp,
                "is_active": s.is_active,
                "notes": s.notes,
            }
            for s in shoes
        ]


@mcp.tool()
def get_retailers(scraping_enabled: Optional[bool] = True) -> List[dict]:
    """
    List retailers this app scrapes for deals.

    Use this to see which retailers are configured and whether scraping is
    currently enabled for each, e.g. before calling trigger_scrape.

    Args:
        scraping_enabled: Filter by whether scraping is enabled for the
            retailer. Defaults to True (only retailers actively scraped).
            Pass None for all retailers, including disabled ones.
    """
    with _core.get_session() as db:
        query = db.query(Retailer).filter(Retailer.is_active == True)
        if scraping_enabled is not None:
            query = query.filter(Retailer.scraping_enabled == scraping_enabled)
        retailers = query.order_by(Retailer.name).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "base_url": r.base_url,
                "platform": r.platform,
                "scraping_enabled": r.scraping_enabled,
                "last_scraped_at": r.last_scraped_at.isoformat() if r.last_scraped_at else None,
            }
            for r in retailers
        ]


@mcp.tool()
def add_shoe(brand: str, model: str, msrp: Optional[float] = None, target_price: Optional[float] = None) -> dict:
    """
    Start tracking a new shoe for deals.

    The shoe is tracked across ALL sizes (sizing is handled per-deal, not
    per-shoe), so don't include a size in the model name. This only adds
    the shoe to the database — call trigger_scrape afterward to actually
    search retailers for it.

    Args:
        brand: Shoe brand, e.g. "Nike".
        model: Shoe model, e.g. "Vaporfly 3" (no size).
        msrp: Manufacturer's list/retail price (CAD). This drives deals — a
            deal is created whenever a retailer's price falls below the MSRP,
            and savings % is measured against it. A shoe with no MSRP is
            tracked but can't produce deals until one is set.
        target_price: Optional personal "ping me at this price" threshold. It
            is stored for reference but does NOT affect deal qualification or
            savings % — MSRP does.
    """
    try:
        with _core.get_session() as db:
            shoe = Shoe(brand=brand.strip(), model=model.strip(), target_price=target_price, msrp=msrp)
            db.add(shoe)
            db.commit()
            db.refresh(shoe)
            return {"success": True, "id": shoe.id, "brand": shoe.brand, "model": shoe.model}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def delete_shoe(shoe_id: int) -> dict:
    """
    Remove a shoe from deal tracking entirely.

    Deletes the shoe and its associated price records and deals from the
    tracked-shoes database. This does NOT affect owned_shoes (personal
    rotation). Use this when you no longer want to monitor a shoe for deals.

    Args:
        shoe_id: ID of the shoe to delete (from get_shoes).
    """
    try:
        with _core.get_session() as db:
            shoe = db.query(Shoe).filter(Shoe.id == shoe_id).first()
            if not shoe:
                return {"success": False, "error": f"No tracked shoe found with id {shoe_id}"}
            name = f"{shoe.brand} {shoe.model}"
            db.delete(shoe)
            db.commit()
            return {"success": True, "deleted": name}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def scrape_health() -> dict:
    """
    Report each retailer's scrape health so you can answer "is any retailer
    quietly broken?" without triggering a scrape.

    For every active retailer this returns a `health` verdict plus the latest
    run's outcome:
      - "ok"      — last scrape finished cleanly and found products.
      - "warning" — last scrape finished cleanly but found ZERO products; the
                    retailer's site likely changed and its scraper needs a look
                    (this is the failure no error would ever show).
      - "error"   — last scrape hit an exception (see the run's `error`).
      - "unknown" — never scraped, or a scrape is currently running.

    Each retailer entry also carries `watchdog_alert` (bool) and
    `watchdog_reason` (str | null) — set when the last 3 completed runs were
    all failures (error or 0-product warning). The top-level
    `retailers_needing_attention` list summarises retailers where the watchdog
    fired so you can spot trouble at a glance without scanning every entry.

    Also returns `recent_runs`, a newest-first log across all retailers. This
    reads the durable scrape_runs history, so it reflects trends across past
    scrapes, not just the current job. Use it before trigger_scrape to decide
    whether a retailer is worth investigating.

    Finally, `needs_onboarding` lists active retailers with no working scraper
    that haven't been declared unscrapable (R4.6) — new retailers awaiting
    setup, distinct from the watchdog's "quietly broken" cases. Run the
    `retailer_onboarding` prompt (or probe_retailer) to resolve them.
    """
    with _core.get_session() as db:
        return scrape_history_svc.scrape_health(db)


@mcp.tool()
async def trigger_scrape(ctx: Context, shoe_id: Optional[int] = None) -> dict:
    """
    Scrape retailers for current prices and detect new deals.

    Scrapes one shoe if shoe_id is given, otherwise every actively-tracked
    shoe across every enabled retailer — which can take a while (it's a
    real, synchronous scrape of live retailer sites, not a queued job).
    Calls the same ScrapeOrchestrator the REST API's /api/scrape endpoints use.
    If a scrape is already running (from this tool, the REST API, or the
    UI), returns success=False immediately rather than starting another
    one on top of it — do not just retry in a loop; wait and check
    get_dashboard_stats' last_scrape instead.

    Args:
        shoe_id: ID of a specific shoe to scrape (from get_shoes). Omit to
            scrape every active shoe.
    """
    with _core.get_session() as db:
        manager = ScrapeOrchestrator(db)
        try:
            with scrape_guard():
                if shoe_id is not None:
                    shoe = db.query(Shoe).filter(Shoe.id == shoe_id).first()
                    if not shoe:
                        return {"success": False, "error": f"Shoe with id {shoe_id} not found"}
                    results = manager.scrape_shoe(shoe_id)
                else:
                    results = manager.scrape_all_shoes()
        except ScrapeInProgressError as e:
            return {"success": False, "error": str(e)}

        try:
            # results is always a dict (scrape_shoe → "deals_found";
            # scrape_all_shoes → "total_deals_found"). The old code iterated
            # it as a list, which gave string keys — deals_found was always 0.
            if shoe_id is not None:
                deals_found = results.get("deals_found", 0)
                shoes_count = 1
            else:
                deals_found = results.get("total_deals_found", 0)
                shoes_count = results.get("total_shoes", 0)
            await ctx.log(
                "info",
                f"Scrape completed: {shoes_count} shoe(s) scraped, {deals_found} deal(s) found.",
                logger_name="scraper",
            )
        except Exception:
            pass

        return {"success": True, "results": results}


@mcp.tool()
def get_dashboard_stats() -> dict:
    """
    Get an overview of tracked shoes, retailers, active deals, and the
    average savings across active deals — the same numbers shown on the
    app's Dashboard page. Useful for "how's it going" / "give me a summary"
    style questions.
    """
    with _core.get_session() as db:
        last_scrape_record = (
            db.query(Retailer.last_scraped_at).order_by(desc(Retailer.last_scraped_at)).first()
        )
        avg_savings = (
            db.query(func.avg(Deal.savings_amount)).filter(Deal.is_active == True).scalar()
        )
        return {
            "total_shoes": db.query(Shoe).count(),
            "active_shoes": db.query(Shoe).filter(Shoe.is_active == True).count(),
            "total_retailers": db.query(Retailer).count(),
            "active_retailers": db.query(Retailer).filter(Retailer.is_active == True).count(),
            "active_deals": db.query(Deal).filter(Deal.is_active == True).count(),
            "total_price_records": db.query(PriceRecord).count(),
            "last_scrape": last_scrape_record[0].isoformat() if last_scrape_record and last_scrape_record[0] else None,
            "average_savings": float(avg_savings) if avg_savings else None,
        }


@mcp.tool()
def get_price_history(shoe_id: int, limit: int = 50) -> List[dict]:
    """
    Get recent scraped prices for one shoe across all retailers, newest
    first. Use this to answer "how has the price of X moved" or "what's
    the lowest it's been at retailer Y" type questions.

    Args:
        shoe_id: ID of the shoe (from get_shoes).
        limit: Max number of price records to return (default 50, capped at 200).
    """
    limit = max(1, min(limit, 200))
    with _core.get_session() as db:
        shoe = db.query(Shoe).filter(Shoe.id == shoe_id).first()
        if not shoe:
            return []
        records = (
            db.query(PriceRecord)
            .filter(PriceRecord.shoe_id == shoe_id)
            .order_by(desc(PriceRecord.scraped_at))
            .limit(limit)
            .all()
        )
        return [
            {
                "retailer": r.retailer.name,
                "price": r.price,
                "original_price": r.original_price,
                "in_stock": r.in_stock,
                "colorway": r.colorway,
                "scraped_at": r.scraped_at.isoformat() if r.scraped_at else None,
            }
            for r in records
        ]


@mcp.resource(
    "shoes://deals/active",
    name="Active Deals",
    description="Current active shoe deals sorted by savings percentage",
    mime_type="application/json",
)
def active_deals_resource() -> str:
    """Top 20 active deals sorted by savings percentage"""
    import json

    with _core.get_session() as db:
        deals = (
            db.query(Deal)
            .filter(Deal.is_active == True)
            .order_by(desc(Deal.savings_percent))
            .limit(20)
            .all()
        )
        total = db.query(Deal).filter(Deal.is_active == True).count()

        md_lines = [
            f"# Active Deals ({total} deals)",
            "",
            "| Shoe | Retailer | Price | Savings |",
            "|------|----------|-------|---------|",
        ]
        for d in deals:
            shoe_name = f"{d.shoe.brand} {d.shoe.model}"
            savings = f"{round(d.savings_percent)}% off"
            md_lines.append(f"| {shoe_name} | {d.retailer.name} | ${d.current_price:.2f} | {savings} |")

        markdown = "\n".join(md_lines)
        payload = json.dumps({"total": total, "deals": [_deal_to_dict(d) for d in deals]}, default=str)
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "deals://watchlist",
    name="Deals Watchlist",
    description="All tracked shoes — on-sale first with savings, then watching with best-ever price",
    mime_type="application/json",
)
def deals_watchlist_resource() -> str:
    """Full watchlist for chat pre-priming: on-sale shoes first, watching shoes second."""
    import json

    with _core.get_session() as db:
        entries = watchlist_svc.build_watchlist(db)

    on_sale = [e for e in entries if e.on_sale]
    watching = [e for e in entries if not e.on_sale]

    md_lines = [f"# Deals Watchlist ({len(entries)} shoes tracked)", ""]

    if on_sale:
        md_lines += [
            f"## On Sale Now ({len(on_sale)})",
            "",
            "| Shoe | Type | Best Price | Savings | Best Ever |",
            "|------|------|-----------|---------|-----------|",
        ]
        for e in on_sale:
            name = f"{e.brand} {e.model}"
            type_tag = e.shoe_type or "—"
            if e.best_deal:
                price = f"${e.best_deal.current_price:.2f} @ {e.best_deal.retailer_name}"
                savings = f"{round(e.best_deal.savings_percent)}% off"
            else:
                price = savings = "—"
            best_ever = f"${e.best_ever_price:.2f}" if e.best_ever_price else "—"
            md_lines.append(f"| {name} | {type_tag} | {price} | {savings} | {best_ever} |")

    if watching:
        md_lines += [
            "",
            f"## Watching ({len(watching)})",
            "",
            "| Shoe | Type | MSRP | Best Ever |",
            "|------|------|------|-----------|",
        ]
        for e in watching:
            name = f"{e.brand} {e.model}"
            type_tag = e.shoe_type or "—"
            msrp = f"${e.msrp:.2f}" if e.msrp else "—"
            best_ever = f"${e.best_ever_price:.2f}" if e.best_ever_price else "—"
            md_lines.append(f"| {name} | {type_tag} | {msrp} | {best_ever} |")

    markdown = "\n".join(md_lines)
    payload = json.dumps({"entries": [_watchlist_entry_payload(e) for e in entries]}, default=str)
    return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "shoes://retailers",
    name="Retailers",
    description="Active retailers being scraped with last scraped timestamp and scraping status",
    mime_type="application/json",
)
def retailers_resource() -> str:
    """Active retailers with last-scraped relative timestamps"""
    import json

    with _core.get_session() as db:
        retailers = (
            db.query(Retailer)
            .filter(Retailer.is_active == True)
            .order_by(Retailer.name)
            .all()
        )

        md_lines = ["# Retailers", "", "| Name | Scraping | Last Scraped |", "|------|----------|-------------|"]
        retailer_dicts = []
        for r in retailers:
            status = "✅ enabled" if r.scraping_enabled else "⏸ disabled"
            last = _format_relative_time(r.last_scraped_at)
            md_lines.append(f"| {r.name} | {status} | {last} |")
            retailer_dicts.append({
                "id": r.id,
                "name": r.name,
                "base_url": r.base_url,
                "platform": r.platform,
                "scraping_enabled": r.scraping_enabled,
                "last_scraped_at": r.last_scraped_at.isoformat() if r.last_scraped_at else None,
                "last_scraped_relative": _format_relative_time(r.last_scraped_at),
            })

        markdown = "\n".join(md_lines)
        payload = json.dumps({"retailers": retailer_dicts}, default=str)
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "shoes://deals/{brand}",
    name="Brand Deals",
    description="Active deals filtered by brand name",
    mime_type="application/json",
)
def brand_deals_resource(brand: str) -> str:
    """Active deals for a specific brand, sorted by savings percentage"""
    import json

    with _core.get_session() as db:
        deals = (
            db.query(Deal)
            .join(Deal.shoe)
            .filter(Deal.is_active == True, Shoe.brand.ilike(f"%{brand}%"))
            .order_by(desc(Deal.savings_percent))
            .all()
        )

        if not deals:
            return f"No active deals found for {brand}"

        md_lines = [
            f"# Active Deals — {brand} ({len(deals)} deal{'s' if len(deals) != 1 else ''})",
            "",
            "| Shoe | Retailer | Price | Savings |",
            "|------|----------|-------|---------|",
        ]
        for d in deals:
            shoe_name = f"{d.shoe.brand} {d.shoe.model}"
            savings = f"{round(d.savings_percent)}% off"
            md_lines.append(f"| {shoe_name} | {d.retailer.name} | ${d.current_price:.2f} | {savings} |")

        markdown = "\n".join(md_lines)
        payload = json.dumps({"brand": brand, "deals": [_deal_to_dict(d) for d in deals]}, default=str)
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.tool()
def get_deal_alerts() -> dict:
    """
    Detect new deal events since the last check and advance the high-water mark.

    Returns a DealAlertDigest covering three alert types:
      - new_deals: tracked shoes whose price fell below MSRP (or re-qualified)
        since the last check, sorted by deepest discount first.
      - price_drops: pre-existing active deals where a subsequent scrape found
        a lower price than the reference price at the last check, sorted by
        largest drop amount first. New deals are excluded to avoid double-counting.
      - replacement_alerts: owned shoes in the retirement pipeline (≥ 75% of
        mileage_limit) that have new type-matching deals available since the
        last check (cross-domain bridge via shoe_type heuristic).

    First call ever (no high-water mark in AppSettings) defaults to a 7-day
    window and sets first_run=True in the response — a reasonable catch-up
    window without flooding the first report.

    If the runner has set a shoe size (Settings → preferred size), new_deals and
    price_drops exclude deals whose listed sizes don't include it (deals with
    unknown sizes are kept); out_of_size_suppressed reports how many were left
    out so you can mention it.

    The high-water mark (AppSettings key "last_deal_alert_check_at") is updated
    on every call; subsequent calls report only incremental events.

    Use this to answer "any new deals since yesterday?" or before presenting
    the deal_alert_digest prompt for a structured briefing. Read-only with
    respect to deals — the only write is the settings high-water mark.
    """
    with _core.get_session() as db:
        last_check_str = settings_svc.get_setting(db, "last_deal_alert_check_at")
        since: Optional[datetime] = None
        if last_check_str:
            try:
                # strip tzinfo — SQLite comparisons need naive datetimes
                since = datetime.fromisoformat(last_check_str).replace(tzinfo=None)
            except ValueError:
                since = None

        digest = deal_alerts_svc.deal_alerts(db, since=since)

        # Advance the high-water mark so next call only reports incremental events
        settings_svc.set_setting(db, "last_deal_alert_check_at", digest.checked_at)
        db.commit()

    def _new_deal_to_dict(a) -> dict:
        return {
            "deal_id": a.deal_id, "brand": a.brand, "model": a.model,
            "shoe_type": a.shoe_type, "retailer": a.retailer,
            "current_price": a.current_price, "msrp": a.msrp,
            "savings_percent": a.savings_percent, "savings_amount": a.savings_amount,
            "detected_at": a.detected_at, "product_url": a.product_url,
        }

    def _drop_to_dict(a) -> dict:
        return {
            "deal_id": a.deal_id, "brand": a.brand, "model": a.model,
            "retailer": a.retailer, "old_price": a.old_price, "new_price": a.new_price,
            "drop_amount": a.drop_amount, "drop_percent": a.drop_percent,
            "msrp": a.msrp, "savings_percent": a.savings_percent,
            "scraped_at": a.scraped_at, "product_url": a.product_url,
        }

    def _replacement_to_dict(a) -> dict:
        return {
            "owned_shoe_id": a.owned_shoe_id, "brand": a.brand, "model": a.model,
            "nickname": a.nickname, "pct": a.pct, "shoe_type": a.shoe_type,
            "forecast_status": a.forecast_status, "weeks_to_limit": a.weeks_to_limit,
            "projected_limit_date": a.projected_limit_date,
            "new_deals": a.new_deals,
        }

    return {
        "since": digest.since,
        "checked_at": digest.checked_at,
        "first_run": digest.first_run,
        "has_alerts": digest.has_alerts,
        "out_of_size_suppressed": digest.out_of_size_suppressed,
        "new_deals": [_new_deal_to_dict(a) for a in digest.new_deals],
        "price_drops": [_drop_to_dict(a) for a in digest.price_drops],
        "replacement_alerts": [_replacement_to_dict(a) for a in digest.replacement_alerts],
    }


@mcp.prompt()
def deal_alert_digest() -> str:
    """
    Generate the deal alert digest — new deals, price drops, and replacement
    suggestions for shoes in the retirement pipeline, since the last check.
    Advances the high-water mark so subsequent calls only show incremental alerts.
    Read-only from the user's perspective (the only write is the settings watermark).
    """
    return """# Deal Alert Digest Agent

You are generating the runner's deal alert briefing. This is READ-ONLY —
no deal writes, no shoe modifications, no confirmation gates.

## Step 1 — Fetch the alert digest
Call `get_deal_alerts()`. It checks for new deal events since the last run
and advances the high-water mark automatically. Do not call it more than once.

## Step 2 — Present the digest
Use the structure below. Omit any section whose list is empty.

---
**Deal Alert Digest**
_Since: [since if not null, else "last 7 days (first run)"] · Checked: [checked_at]_

### New Deals ([count])
[For each entry in new_deals, sorted by savings_percent descending:]
- **[brand] [model]** ([shoe_type or "—"]) — $[current_price] @ [retailer]
  [savings_percent rounded to 0dp]% off MSRP ($[msrp]) · saves $[savings_amount rounded to 2dp]
  [product_url]

### Price Drops ([count])
[For each entry in price_drops, sorted by drop_amount descending:]
- **[brand] [model]** @ [retailer] — $[old_price] → $[new_price] (↓ $[drop_amount rounded to 2dp] / [drop_percent rounded to 0dp]%)
  Now [savings_percent rounded to 0dp]% off MSRP ($[msrp])
  [product_url]

### Replacement Suggestions ([count])
[For each entry in replacement_alerts:]
- **[brand] [model]**[" ([nickname])" if nickname] — [pct×100 rounded to 0dp]% of mileage limit
  Type: [shoe_type] · [count of new_deals] new deal(s) available:
  [For each deal in new_deals:
    – [deal.brand] [deal.model] @ [deal.retailer] — $[deal.current_price] ([deal.savings_percent rounded to 0dp]% off)
      [deal.product_url]]

[If has_alerts is False:]
No new deal events since [since if set, else "the last 7 days"]. All quiet.
---

## Rules
- Never invent deal data not present in the get_deal_alerts response
- If first_run is True, note in the header that this is the first check
  (7-day default window applied)
- pct display: multiply by 100 and round to the nearest whole number
  (e.g. 0.834 → 83%)
- savings_percent / drop_percent: round to nearest whole number
- savings_amount / drop_amount / prices: format to 2 decimal places
- Replacement alerts bridge the deals and rotation domains via shoe_type —
  the runner still needs to decide whether to buy; do not recommend
- Keep the tone direct and concise; include the product_url for every deal
  so the runner can click through immediately
"""


# ---------------------------------------------------------------------------
# R4.4 — Coupon Hunting Agent
# ---------------------------------------------------------------------------

@mcp.tool()
def get_coupon_opportunities() -> dict:
    """
    Return active promo codes per retailer, annotated with active deals.

    "Stackable" means the retailer has BOTH an active promo code AND at
    least one active deal (price below MSRP) right now — applying the code
    on top of the deal compounds the saving.

    Returns:
        all_retailers      every active retailer with ≥1 active promo code
        stackable          subset that also has active deals (the opportunities)
        total_active_codes count of active promo codes across all retailers
        stackable_count    len(stackable)

    Read-only — no scraping triggered. Call hunt_coupons first if the codes
    feel stale (check last_seen_at in each promo code entry).
    """
    with _core.get_session() as db:
        return coupon_hunter_svc.get_stacking_opportunities(db)


@mcp.tool()
def hunt_coupons() -> dict:
    """
    Scan every active retailer's homepage (and any additional promo pages
    they advertise) for discount codes, persisting any found in the
    promo_codes table. Scraped codes never overwrite manually-added ones.

    This is a synchronous network operation — expects 10–60 s depending on
    retailer count and whether any retailers use a headless browser. It does
    NOT hold the scrape lock (promo hunting only reads pages and writes to
    promo_codes; it never touches deals or prices).

    Returns retailers_scanned, codes_found, new_codes, errors.
    Call get_coupon_opportunities after to see the updated stacking picture.
    """
    with _core.get_session() as db:
        result = ScrapeOrchestrator(db).detect_all_promo_codes()
        return {
            "success": True,
            "retailers_scanned": result["retailers_scanned"],
            "codes_found": result["codes_found"],
            "new_codes": result["new_codes"],
            "errors": result["errors"],
        }


@mcp.prompt()
def coupon_digest() -> str:
    """Guided workflow to surface coupon stacking opportunities."""
    return """\
You are helping Anton find opportunities to stack retailer promo codes on top
of existing shoe deals.  Stacking = a retailer that currently has BOTH an
active deal (price below MSRP) AND an active promo code, so the runner can
apply the code at checkout for a compound saving.

## Steps

1. Call `get_coupon_opportunities` to read the current DB state.

2. Check freshness: if `total_active_codes` is 0, or any code's `last_seen_at`
   is more than 3 days ago, offer to call `hunt_coupons` to refresh. After
   hunting, call `get_coupon_opportunities` again.

3. Report the `stackable` retailers — for each one show:
   - **Retailer name**
   - Active promo codes: code, description, estimated % off
   - Active deals: shoe name, current price, % below MSRP, product URL
   - Estimated combined saving (deal % + promo %, noting they may not simply
     add — present the math honestly, e.g. "20% off already-sale price")

4. If no `stackable` entries exist, list the `all_retailers` entries
   (retailers with codes but no current deals) as "codes to keep in mind."

5. Highlight the **single best opportunity**: the stackable entry with the
   largest combined saving potential.

## Rules
- Do not purchase or apply codes — present the opportunity for the runner.
- If `errors` came back from `hunt_coupons`, report them briefly.
- Keep savings estimates honest: note when a promo applies to the already-
  discounted price vs the original MSRP (compounding, not additive).
"""
