"""
MCP server exposing this app's core functionality as tools for LLM clients.

Mounted onto the FastAPI app (see app/main.py) at /mcp via
mcp.streamable_http_app(), using Streamable HTTP transport.

Tools stay thin on purpose: they read the same SQLAlchemy models and call
the same ScrapeOrchestrator the REST routers (app/routers/*.py) use, so there is
exactly one place business logic lives. Each tool opens its own DB session
(FastMCP tools aren't FastAPI route handlers, so they can't use
Depends(get_db)) and closes it when done, mirroring get_db's lifecycle.
"""
from contextlib import contextmanager
from typing import List, Optional

from mcp import types as mcp_types
from mcp.server.fastmcp import FastMCP, Context
from sqlalchemy import desc, func
from sqlalchemy.orm import contains_eager

from datetime import date as date_type, datetime, timezone

from app.coros_client import get_coros_config
from app.database import SessionLocal
from app.models.models import Activity, Deal, OwnedShoe, PriceRecord, Retailer, Shoe, ShoeNote, ShoeRun
from app.scrapers.orchestrator import ScrapeOrchestrator
from app.scrapers.lock import ScrapeInProgressError, scrape_guard
from app.services import rotation, coros as coros_svc, settings as settings_svc, strava_stats, races as races_svc, fitness as fitness_svc, scrape_history as scrape_history_svc, deals as deals_svc, weekly_summary as weekly_summary_svc, watchlist as watchlist_svc, deal_alerts as deal_alerts_svc, race_advisor as race_advisor_svc, coupon_hunter as coupon_hunter_svc
from app.utils.activity_tags import ACTIVITY_TAGS, is_valid_tag

# streamable_http_path="/" because the app this is mounted under (see
# main.py) already adds the "/mcp" prefix — without this override the route
# would only be reachable at the doubled-up "/mcp/mcp".
mcp = FastMCP("running-shoe-deals", streamable_http_path="/")


@contextmanager
def get_session():
    """Same open/close lifecycle as app.database.get_db, for use outside FastAPI's DI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        "colorway": deal.colorway,
        "product_url": deal.product_url,
        "detected_at": deal.detected_at.isoformat() if deal.detected_at else None,
    }


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
            e.g. "10.5". Sizes are matched exactly as recorded by the scraper.
        shoe_type: Filter by shoe category, e.g. "long_distance_racer",
            "daily_trainer", "tempo", "trail", "recovery", "intervals",
            "short_distance_racer".
        limit: Max number of deals to return (default 20, capped at 100).
    """
    limit = max(1, min(limit, 100))
    with get_session() as db:
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
    with get_session() as db:
        deals = deals_svc.list_deals(db, brand=brand, model=model)
        return [_deal_to_dict(d) for d in deals]


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
    with get_session() as db:
        entries = watchlist_svc.build_watchlist(db)
        return [_watchlist_entry_to_dict(e) for e in entries]


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
    with get_session() as db:
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
    with get_session() as db:
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
        with get_session() as db:
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
        with get_session() as db:
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
    """
    with get_session() as db:
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
    with get_session() as db:
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
            deals_found = sum(r.get("deals_found", 0) for r in results if isinstance(r, dict))
            await ctx.log(
                "info",
                f"Scrape completed: {len(results)} shoe(s) scraped, {deals_found} deal(s) found.",
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
    with get_session() as db:
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
    with get_session() as db:
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


@mcp.tool()
def get_owned_shoes(status_filter: Optional[str] = None) -> List[dict]:
    """
    List shoes in the user's personal rotation with current mileage and
    status. Use this for "what shoes do I have", "which shoes are near
    retirement", or to look up an owned_shoe_id before calling another tool.

    Args:
        status_filter: Filter by status — "active", "retired", or
            "for_sale". Omit for all shoes regardless of status.
    """
    with get_session() as db:
        query = db.query(OwnedShoe)
        if status_filter:
            query = query.filter(OwnedShoe.status == status_filter)
        shoes = query.order_by(OwnedShoe.created_at.desc()).all()
        return [_owned_shoe_to_dict(s, rotation.compute_lifetime_stats(db, s.id)) for s in shoes]


@mcp.tool()
def get_shoe_runs(owned_shoe_id: int) -> dict:
    """
    Get the run history logged against an owned shoe (newest first), plus
    that shoe's lifetime average pace, average heart rate, and run count.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
    """
    with get_session() as db:
        runs = (
            db.query(ShoeRun)
            .join(Activity, ShoeRun.activity_id == Activity.id)
            .options(contains_eager(ShoeRun.activity))
            .filter(ShoeRun.owned_shoe_id == owned_shoe_id)
            .order_by(desc(Activity.run_date), desc(ShoeRun.created_at))
            .all()
        )
        stats = rotation.compute_lifetime_stats(db, owned_shoe_id)
        return {
            "owned_shoe_id": owned_shoe_id,
            "runs": [_shoe_run_to_dict(r) for r in runs],
            "lifetime_avg_pace": stats.lifetime_avg_pace,
            "lifetime_avg_hr": stats.lifetime_avg_hr,
            "total_runs": stats.total_runs,
        }


@mcp.tool()
async def log_run_to_shoe(
    owned_shoe_id: int,
    distance_km: float,
    run_date: str,
    ctx: Context,
    avg_pace: Optional[str] = None,
    avg_hr: Optional[int] = None,
    notes: Optional[str] = None,
    name: Optional[str] = None,
    elevation_gain_m: Optional[float] = None,
    moving_time_s: Optional[int] = None,
    elapsed_time_s: Optional[int] = None,
    avg_cadence: Optional[float] = None,
    calories: Optional[float] = None,
    training_load: Optional[float] = None,
    training_focus: Optional[str] = None,
    activity_tag: Optional[str] = None,
) -> dict:
    """
    Log a run against an owned shoe, adding to its current mileage.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
        distance_km: Distance covered in this run, in kilometers.
        run_date: Date of the run, in YYYY-MM-DD format.
        avg_pace: Optional average pace for the run, format "M:SS/km"
            (e.g. "3:52/km").
        avg_hr: Optional average heart rate for the run, in beats per minute.
        notes: Optional notes about the run.
        name: Activity name/title (e.g. "Morning Run").
        elevation_gain_m: Total ascent in metres.
        moving_time_s: Moving time in seconds.
        elapsed_time_s: Elapsed (wall-clock) time in seconds.
        avg_cadence: Average cadence in steps/min.
        calories: Energy in kcal.
        training_load: Training-load score.
        training_focus: Coaching label (e.g. "Aerobic base").
        activity_tag: One of the ACTIVITY_TAGS vocabulary values (Easy, Long
            Run, Recovery, Tempo, Intervals, Track, Workout, Trail, Parkrun,
            Race). Only pass a tag the runner has CONFIRMED (C9).
    """
    if activity_tag is not None and not is_valid_tag(activity_tag):
        return {
            "success": False,
            "error": f"'{activity_tag}' is not a valid activity_tag. "
                     f"Use one of: {', '.join(ACTIVITY_TAGS)}.",
        }
    try:
        with get_session() as db:
            shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
            if not shoe:
                return {"success": False, "error": f"Owned shoe with id {owned_shoe_id} not found"}
            old_mileage = shoe.current_mileage

            result = rotation.log_run(
                db,
                owned_shoe_id,
                distance_km=distance_km,
                run_date=date_type.fromisoformat(run_date),
                avg_pace=avg_pace,
                avg_hr=avg_hr,
                notes=notes,
                name=name,
                elevation_gain_m=elevation_gain_m,
                moving_time_s=moving_time_s,
                elapsed_time_s=elapsed_time_s,
                avg_cadence=avg_cadence,
                calories=calories,
                training_load=training_load,
                training_focus=training_focus,
                activity_tag=activity_tag,
            )
            shoe = result.shoe

            thresholds = [
                (600, "approaching end of life — start thinking about replacement"),
                (700, "consider retiring soon — performance may be degrading"),
                (800, "past recommended limit — retire this shoe"),
            ]
            threshold_crossed = None
            threshold_message = None
            for threshold_km, message in thresholds:
                if old_mileage < threshold_km <= shoe.current_mileage:
                    threshold_crossed = threshold_km
                    threshold_message = message
                    break

            if threshold_crossed is not None:
                try:
                    await ctx.log(
                        "warning",
                        f"⚠️ {shoe.brand} {shoe.model} has reached {threshold_crossed}km — {threshold_message}.",
                        logger_name="shoe-tracker",
                    )
                except Exception:
                    pass

            return {
                "success": True,
                "run_id": result.run.id,
                "shoe": f"{shoe.brand} {shoe.model}",
                "new_mileage": round(shoe.current_mileage, 2),
                "checkpoint_reached": result.checkpoint_reached,
                "checkpoint_km": result.checkpoint_km,
                "threshold_crossed": threshold_crossed,
                "threshold_message": threshold_message,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def delete_shoe_run(run_id: int) -> dict:
    """
    Delete a logged run, subtracting its distance back out of the parent
    shoe's current mileage.

    Args:
        run_id: ID of the run to delete (from get_shoe_runs).
    """
    try:
        with get_session() as db:
            run = db.query(ShoeRun).filter(ShoeRun.id == run_id).first()
            if not run:
                return {"success": False, "error": f"Run with id {run_id} not found"}
            distance = run.activity.distance_km if run.activity else None
            try:
                shoe = rotation.delete_run(db, run_id)
            except LookupError as exc:
                return {"success": False, "error": str(exc)}
            return {"success": True, "removed_km": distance, "updated_mileage": round(shoe.current_mileage, 2)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_shoe_notes(owned_shoe_id: int) -> List[dict]:
    """
    Get the notes journal for an owned shoe (feel, observations, mileage
    checkpoints), newest first — replaces the old single free-text notes
    field with a timestamped, mileage-anchored history.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
    """
    with get_session() as db:
        notes = (
            db.query(ShoeNote)
            .filter(ShoeNote.owned_shoe_id == owned_shoe_id)
            .order_by(desc(ShoeNote.created_at))
            .all()
        )
        return [_shoe_note_to_dict(n) for n in notes]


@mcp.tool()
def add_shoe_note(owned_shoe_id: int, body: str) -> dict:
    """
    Add a manual journal entry to an owned shoe's notes. The shoe's current
    mileage at the time of writing is recorded automatically alongside it.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
        body: The note content.
    """
    try:
        with get_session() as db:
            try:
                note = rotation.add_note(db, owned_shoe_id, body)
            except LookupError as exc:
                return {"success": False, "error": str(exc)}
            shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
            return {
                "success": True,
                "note_id": note.id,
                "shoe": f"{shoe.brand} {shoe.model}",
                "mileage_at_note": note.mileage_at_note,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def draft_shoe_review(owned_shoe_id: int, ctx: Context) -> dict:
    """
    Draft a structured shoe review based on logged notes and run history
    for a specific owned shoe. Uses MCP sampling to generate the review
    text via the connected client's LLM — the server sends a sampling
    request back through the MCP protocol and the client handles the LLM
    call. Returns a structured review draft ready for editing and posting.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
    """
    with get_session() as db:
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
        if not shoe:
            return {"success": False, "error": "Shoe not found"}

        notes = (
            db.query(ShoeNote)
            .filter(ShoeNote.owned_shoe_id == owned_shoe_id)
            .order_by(ShoeNote.created_at)
            .all()
        )
        if not notes:
            return {
                "success": False,
                "error": "No notes found for this shoe. Add some notes first via add_shoe_note.",
            }

        runs = (
            db.query(ShoeRun)
            .join(Activity, ShoeRun.activity_id == Activity.id)
            .options(contains_eager(ShoeRun.activity))
            .filter(ShoeRun.owned_shoe_id == owned_shoe_id)
            .order_by(Activity.run_date)
            .all()
        )

        stats = rotation.compute_lifetime_stats(db, owned_shoe_id)
        total_runs = stats.total_runs
        lifetime_avg_pace = stats.lifetime_avg_pace or "—"
        lifetime_avg_hr = stats.lifetime_avg_hr

        first_run_date = runs[0].activity.run_date.isoformat() if runs and runs[0].activity.run_date else "—"
        last_run_date = runs[-1].activity.run_date.isoformat() if runs and runs[-1].activity.run_date else "—"

        formatted_notes = "\n".join(
            f"- [{round(n.mileage_at_note)}km · {n.created_at.strftime('%Y-%m-%d') if n.created_at else '—'}] {n.body}"
            for n in notes
        )

        nickname_part = f" ({shoe.nickname})" if shoe.nickname else ""
        shoe_type = shoe.shoe_type or "unspecified"
        avg_hr_str = f"{lifetime_avg_hr}bpm" if lifetime_avg_hr else "—"

        context = f"""Shoe: {shoe.brand} {shoe.model}{nickname_part}
Type: {shoe_type}
Total distance: {round(shoe.current_mileage, 1)}km over {total_runs} runs
Period: {first_run_date} to {last_run_date}
Avg pace: {lifetime_avg_pace} | Avg HR: {avg_hr_str}
Status: {shoe.status}

Notes logged during use:
{formatted_notes}"""

        sampling_prompt = f"""Based on the following running shoe data and personal notes, write a structured shoe review suitable for posting on Reddit (r/RunningShoeGeeks or similar subreddit).

{context}

Format the review as:
## [Shoe Name] Review — [Total Distance]km

**The Shoe:** [1-2 sentence overview]

**What I Used It For:** [workout types based on shoe_type and pace data]

**The Good:** [positive observations from notes]

**The Bad:** [negative observations or limitations from notes]

**Mileage & Durability:** [observations about how it held up]

**Who Is It For:** [recommendation based on shoe_type and experience]

**Verdict:** [1-2 sentence summary and rating /10]

Keep it honest, specific, and useful. Use the notes as the primary source — do not invent observations not present in the notes."""

    try:
        result = await ctx.session.create_message(
            messages=[
                mcp_types.SamplingMessage(
                    role="user",
                    content=mcp_types.TextContent(type="text", text=sampling_prompt),
                )
            ],
            max_tokens=1000,
        )
        review_text = (
            result.content.text
            if isinstance(result.content, mcp_types.TextContent)
            else str(result.content)
        )
        # Auto-save the draft to the shoe so the runner can retrieve it later
        # without re-running the workflow. save_shoe_review overwrites this if
        # the runner edits the text and calls save_shoe_review explicitly.
        with get_session() as save_db:
            rotation.store_shoe_review(save_db, owned_shoe_id, review_text)
        return {
            "success": True,
            "shoe": f"{shoe.brand} {shoe.model}",
            "mileage": round(shoe.current_mileage, 1),
            "review_draft": review_text,
            "saved": True,
            "note": "Draft saved to the shoe. Edit it and call save_shoe_review to update the stored version.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Connected client does not support sampling. Try this tool from Claude Desktop. ({e})",
        }


@mcp.tool()
def save_shoe_review(owned_shoe_id: int, review_text: str) -> dict:
    """
    Persist a runner-edited shoe review draft on an owned shoe (R3.3).

    Call this after the runner has edited the text produced by draft_shoe_review.
    Overwrites the previously stored draft — only one review per shoe is kept.
    The stored text is returned by the shoes://review/{id} resource and exposed
    on the shoe via GET /api/owned-shoes/{id}.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
        review_text: The final (or further-edited) review text to store.
    """
    if not review_text or not review_text.strip():
        return {"success": False, "error": "review_text must not be empty"}
    try:
        with get_session() as db:
            try:
                shoe = rotation.store_shoe_review(db, owned_shoe_id, review_text)
            except LookupError as exc:
                return {"success": False, "error": str(exc)}
            return {
                "success": True,
                "shoe": f"{shoe.brand} {shoe.model}",
                "review_stored": True,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_coros_sync_status() -> dict:
    """
    Check whether COROS credentials are configured and when the last sync
    ran. Use this before fetch_unsynced_coros_runs to confirm sync is
    available.
    """
    config = get_coros_config()
    with get_session() as db:
        last_sync_str = settings_svc.get_setting(db, "last_coros_sync_at")
    return {
        "coros_configured": config is not None,
        "last_sync_at": last_sync_str,
        "message": (
            "COROS sync is ready. Call fetch_unsynced_coros_runs to pull recent runs."
            if config
            else "COROS sync not configured. Add COROS_ACCESS_TOKEN and COROS_OPEN_ID to your .env."
        ),
    }


@mcp.tool()
def fetch_unsynced_coros_runs(days_back: int = 30) -> dict:
    """
    Fetch recent runs from the COROS API that haven't been logged yet.
    Returns a list of runs for you to present to the user for shoe
    assignment. After the user assigns shoes, call confirm_coros_run for
    each one.

    Args:
        days_back: How many days back to look for runs (default 30).
            After the first sync, pass a smaller window matching the days
            since last_sync_at to avoid refetching old history.
    """
    import requests as _requests
    with get_session() as db:
        try:
            result = coros_svc.fetch_unsynced(db, days_back)
        except _requests.exceptions.RequestException as exc:
            return {"success": False, "coros_configured": True, "error": str(exc)}
        except ValueError as exc:
            return {"success": False, "coros_configured": True, "error": str(exc)}

    if not result.coros_configured:
        return {
            "success": False,
            "coros_configured": False,
            "error": "COROS sync not configured. Add COROS_ACCESS_TOKEN and COROS_OPEN_ID to your .env.",
        }

    return {
        "success": True,
        "coros_configured": True,
        "runs": result.runs,
        "already_synced": result.already_synced,
        "total_fetched": len(result.runs) + result.already_synced,
    }


@mcp.tool()
def confirm_coros_run(
    coros_activity_id: str,
    owned_shoe_id: int,
    date: str,
    distance_km: float,
    avg_pace: Optional[str] = None,
    avg_hr: Optional[int] = None,
    notes: Optional[str] = None,
    name: Optional[str] = None,
    elevation_gain_m: Optional[float] = None,
    moving_time_s: Optional[int] = None,
    elapsed_time_s: Optional[int] = None,
    avg_cadence: Optional[float] = None,
    calories: Optional[float] = None,
    training_load: Optional[float] = None,
    training_focus: Optional[str] = None,
    activity_tag: Optional[str] = None,
) -> dict:
    """
    Log a single COROS run to an owned shoe after the user confirms the
    assignment. Call this once per run after fetching unsynced runs and
    getting the user's shoe choice for each.

    Args:
        coros_activity_id: The COROS labelId for this run.
        owned_shoe_id: ID of the owned shoe to log it against.
        date: Run date in YYYY-MM-DD format.
        distance_km: Distance covered in kilometers.
        avg_pace: Average pace as "M:SS/km", e.g. "4:32/km".
        avg_hr: Average heart rate in bpm.
        notes: Optional notes about this run.
        name: COROS activity name/title (e.g. "Morning Run").
        elevation_gain_m: Total ascent in metres.
        moving_time_s / elapsed_time_s: Moving vs total elapsed time, seconds.
        avg_cadence: Average cadence (steps/min).
        calories: Energy in kcal.
        training_load: COROS training-load score for the run.
        training_focus: COROS coaching label (e.g. "Aerobic base").
        activity_tag: One of the ACTIVITY_TAGS vocabulary values (Easy, Long
            Run, Recovery, Tempo, Intervals, Track, Workout, Trail, Parkrun,
            Race). Only pass a tag the runner has CONFIRMED — never infer and
            apply one silently (C9). Omit if the runner didn't set one.
    """
    if activity_tag is not None and not is_valid_tag(activity_tag):
        return {
            "success": False,
            "error": f"'{activity_tag}' is not a valid activity_tag. "
                     f"Use one of: {', '.join(ACTIVITY_TAGS)}.",
        }
    with get_session() as db:
        try:
            result = coros_svc.confirm_run(
                db,
                coros_activity_id=coros_activity_id,
                owned_shoe_id=owned_shoe_id,
                run_date=date_type.fromisoformat(date),
                distance_km=distance_km,
                avg_pace=avg_pace,
                avg_hr=avg_hr,
                notes=notes,
                name=name,
                elevation_gain_m=elevation_gain_m,
                moving_time_s=moving_time_s,
                elapsed_time_s=elapsed_time_s,
                avg_cadence=avg_cadence,
                calories=calories,
                training_load=training_load,
                training_focus=training_focus,
                activity_tag=activity_tag,
            )
        except LookupError:
            return {"success": False, "error": f"Owned shoe {owned_shoe_id} not found"}

        if result is None:
            return {"success": False, "error": f"Run {coros_activity_id} is already logged"}

        stats = rotation.compute_lifetime_stats(db, result.shoe.id)
        return {
            "success": True,
            "checkpoint_reached": result.checkpoint_reached,
            "checkpoint_km": result.checkpoint_km,
            "shoe": _owned_shoe_to_dict(result.shoe, stats),
        }


@mcp.tool()
def retire_shoe(owned_shoe_id: int) -> dict:
    """
    Mark an owned shoe as retired (status="retired"). Use this when a shoe
    has hit its mileage limit or is otherwise done being used for running.

    Args:
        owned_shoe_id: ID of the owned shoe (from get_owned_shoes).
    """
    try:
        with get_session() as db:
            shoe = db.query(OwnedShoe).filter(OwnedShoe.id == owned_shoe_id).first()
            if not shoe:
                return {"success": False, "error": f"Owned shoe with id {owned_shoe_id} not found"}

            shoe.status = "retired"
            db.commit()
            db.refresh(shoe)

            note_count = db.query(ShoeNote).filter(ShoeNote.owned_shoe_id == owned_shoe_id).count()
            result: dict = {
                "success": True,
                "shoe": f"{shoe.brand} {shoe.model}",
                "final_mileage": round(shoe.current_mileage, 2),
            }
            # Nudge the review workflow when the shoe has logged notes — now is
            # when the runner's experience is freshest (R3.3).
            if note_count > 0:
                result["review_prompt"] = (
                    f"This shoe has {note_count} journal note(s). "
                    f"Run draft_shoe_review({owned_shoe_id}) to write a review "
                    "while the experience is fresh."
                )
            return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def get_training_summary(period: str = "monthly") -> dict:
    """
    Weekly or monthly training aggregates over the full run history (imported
    Strava runs unioned with live COROS/manual runs): total distance, run
    count, average pace, average heart rate, and elevation gain per period
    (newest first).

    Use this for questions like "how much did I run last month", "what were my
    weekly volumes this year", or "how has my average pace trended".

    Args:
        period: "monthly" (default) or "weekly".
    """
    if period not in ("weekly", "monthly"):
        return {"error": "period must be 'weekly' or 'monthly'"}
    with get_session() as db:
        summaries = strava_stats.training_summary(db, period)
        return {
            "period": period,
            "buckets": [
                {
                    "period": s.period,
                    "total_km": s.total_km,
                    "run_count": s.run_count,
                    "avg_pace": s.avg_pace,
                    "avg_hr": s.avg_hr,
                    "elevation_gain_m": s.elevation_gain_m,
                }
                for s in summaries
            ],
        }


@mcp.tool()
def get_personal_bests() -> dict:
    """
    Fastest whole-activity time at each distance band (5k, 10k, half, full)
    across the full run history (imported Strava runs unioned with live COROS/
    manual runs). Each best also reports average pace and HR.

    IMPORTANT: these are *whole-activity* times within a distance tolerance —
    not true segment/split PBs. Describe them that way to the user (e.g. "your
    fastest 10k run", not "your 10k PB").
    """
    with get_session() as db:
        result = strava_stats.personal_bests(db)
        return {
            "note": "Whole-activity average-pace bests within a distance tolerance, not segment PBs.",
            "excluded_count": result.excluded_count,
            "excluded_reason": result.excluded_reason,
            "bests": [
                {
                    "band": b.band,
                    "target_km": b.target_km,
                    "run_date": b.run_date,
                    "name": b.name,
                    "distance_km": b.distance_km,
                    "total_time_s": b.total_time_s,
                    "avg_pace": b.avg_pace,
                    "avg_hr": b.avg_hr,
                    "source": b.source,
                    "shoe": b.shoe,
                    "strava_activity_id": b.strava_activity_id,
                    "activity_id": b.activity_id,
                }
                for b in result.records
            ],
        }


@mcp.tool()
def record_athlete_metrics(
    vo2max: Optional[float] = None,
    threshold_pace_s_per_km: Optional[int] = None,
    race_predictions: Optional[dict] = None,
    running_level: Optional[float] = None,
) -> dict:
    """
    Record a COROS athlete-level fitness snapshot (VO2 max, lactate-threshold
    pace, race predictions, running level) for the Training tab's fitness card.
    Append-only: each call stores one dated snapshot; the card shows the most recent.

    Anton cannot fetch these itself (server-side COROS is dormant). Use the
    sync_fitness prompt to fetch from the COROS MCP and confirm with the runner
    (C9) before calling this.

    Args:
        vo2max: VO2 max in ml/kg/min.
        threshold_pace_s_per_km: lactate-threshold pace, seconds per km
            (e.g. 3:45/km → 225).
        race_predictions: dict of distance_km (as a string key) → predicted time
            in seconds, e.g. {"5.0": 1005, "10.0": 2100, "21.0975": 4620,
            "42.195": 9720}.
        running_level: COROS running level score (a composite fitness rating).
    """
    if vo2max is None and threshold_pace_s_per_km is None and not race_predictions and running_level is None:
        return {"success": False, "error": "Provide at least one metric to record."}
    with get_session() as db:
        snap = fitness_svc.record_snapshot(
            db,
            vo2max=vo2max,
            threshold_pace_s_per_km=threshold_pace_s_per_km,
            race_predictions=race_predictions,
            running_level=running_level,
        )
        return {
            "success": True,
            "captured_at": snap.captured_at.isoformat() if snap.captured_at else None,
            "vo2max": snap.vo2max,
            "threshold_pace_s_per_km": snap.threshold_pace_s_per_km,
            "race_predictions": snap.race_predictions,
            "running_level": snap.running_level,
        }


@mcp.tool()
def get_planned_races() -> dict:
    """
    Upcoming and past races the user is training toward, soonest first. Each
    race includes days_remaining / weeks_remaining and a derived target_pace
    ("M:SS/km") when a target time and distance are set.

    Use this to answer "how many weeks until my next race", to reason about
    where the user is in a training block, or to relate recent volume/pace to
    an upcoming goal. A negative days_remaining means the race is in the past.
    """
    with get_session() as db:
        races = races_svc.list_races(db)
        return {"races": [races_svc.race_to_dict(r) for r in races]}


@mcp.tool()
def get_weekly_summary() -> dict:
    """
    Compile the weekly rotation digest for the current ISO week (Monday–Sunday).

    Returns a structured snapshot covering:
    - Volume: this week's km vs last week, with the delta.
    - Per-shoe usage: km and run count for each shoe used this week, most-used first.
      shoe_type is included so you can contextualise race-shoe vs daily-trainer usage.
    - Retirement pipeline: all active shoes at ≥ 75% of their mileage limit, worst first,
      with a count of matching replacement deals.
    - Notable runs: activities tagged Race, Parkrun, Intervals, Tempo, Long Run, or Track
      (the quality-session tags) — does NOT include Easy/Recovery/Workout.
    - Checkpoints: 100km mileage boundaries crossed by any shoe this week.
    - Next race: the soonest upcoming PlannedRace with days/weeks remaining and target pace.

    Call this before composing the weekly_rotation_summary digest, or to answer
    "how was my week?" / "what shoes am I using most?". Read-only — no writes.
    """
    with get_session() as db:
        s = weekly_summary_svc.weekly_summary(db)
        return {
            "week": {"start": s.week_start, "end": s.week_end},
            "volume": {
                "this_week_km": s.this_week_km,
                "last_week_km": s.last_week_km,
                "delta_km": s.delta_km,
            },
            "per_shoe_usage": [
                {
                    "shoe_id": u.shoe_id,
                    "brand": u.brand,
                    "model": u.model,
                    "nickname": u.nickname,
                    "shoe_type": u.shoe_type,
                    "km_this_week": u.km_this_week,
                    "run_count": u.run_count,
                }
                for u in s.per_shoe_usage
            ],
            "pipeline": [
                {
                    "shoe_id": p.shoe_id,
                    "brand": p.brand,
                    "model": p.model,
                    "nickname": p.nickname,
                    "pct": p.pct,
                    "current_mileage": p.current_mileage,
                    "mileage_limit": p.mileage_limit,
                    "replacement_deals": p.replacement_deals,
                }
                for p in s.pipeline
            ],
            "notable_runs": [
                {
                    "run_date": n.run_date,
                    "distance_km": n.distance_km,
                    "avg_pace": n.avg_pace,
                    "avg_hr": n.avg_hr,
                    "activity_tag": n.activity_tag,
                    "name": n.name,
                    "shoe": n.shoe,
                }
                for n in s.notable_runs
            ],
            "checkpoints_this_week": [
                {
                    "shoe_id": c.shoe_id,
                    "brand": c.brand,
                    "model": c.model,
                    "checkpoint_km": c.checkpoint_km,
                    "triggered_at": c.triggered_at,
                }
                for c in s.checkpoints_this_week
            ],
            "next_race": (
                {
                    "name": s.next_race.name,
                    "race_date": s.next_race.race_date,
                    "days_remaining": s.next_race.days_remaining,
                    "weeks_remaining": s.next_race.weeks_remaining,
                    "distance_km": s.next_race.distance_km,
                    "target_pace": s.next_race.target_pace,
                }
                if s.next_race else None
            ),
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


# ---------------------------------------------------------------------------
# Static resources
# ---------------------------------------------------------------------------

@mcp.resource(
    "shoes://rotation",
    name="My Shoe Rotation",
    description="Current owned shoe rotation with mileage, status and lifetime stats for all active shoes",
    mime_type="application/json",
)
def shoe_rotation_resource() -> str:
    """Current owned shoe rotation with mileage and lifetime stats"""
    import json

    with get_session() as db:
        shoes = db.query(OwnedShoe).order_by(OwnedShoe.created_at.desc()).all()
        active = [s for s in shoes if s.status == "active"]
        retired = [s for s in shoes if s.status != "active"]

        md_lines = ["# My Shoe Rotation", "", "**Active Shoes**"]
        shoe_dicts = []
        for s in active:
            stats = rotation.compute_lifetime_stats(db, s.id)
            bar = _format_mileage_bar(s.current_mileage, s.mileage_limit)
            label = s.nickname or ""
            name = f"{s.brand} {s.model}" + (f" ({label})" if label else "")
            pace = stats.lifetime_avg_pace or "—"
            hr = f"{stats.lifetime_avg_hr}bpm" if stats.lifetime_avg_hr else "—"
            runs = stats.total_runs
            type_tag = f" [{s.shoe_type}]" if s.shoe_type else ""
            md_lines.append(f"- {name}{type_tag} — {round(s.current_mileage)}km  {bar}")
            md_lines.append(f"  Avg pace: {pace} · Avg HR: {hr} · {runs} runs")
            shoe_dicts.append(_owned_shoe_to_dict(s, stats))

        if not active:
            md_lines.append("_(none)_")

        if retired:
            md_lines += ["", "**Retired Shoes**"]
            for s in retired:
                stats = rotation.compute_lifetime_stats(db, s.id)
                label = s.nickname or ""
                name = f"{s.brand} {s.model}" + (f" ({label})" if label else "")
                md_lines.append(f"- {name} — {round(s.current_mileage)}km (retired)")
                shoe_dicts.append(_owned_shoe_to_dict(s, stats))

        markdown = "\n".join(md_lines)
        payload = json.dumps({"shoes": shoe_dicts}, default=str)
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "shoes://deals/active",
    name="Active Deals",
    description="Current active shoe deals sorted by savings percentage",
    mime_type="application/json",
)
def active_deals_resource() -> str:
    """Top 20 active deals sorted by savings percentage"""
    import json

    with get_session() as db:
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

    with get_session() as db:
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
    payload = json.dumps({"entries": [_watchlist_entry_to_dict(e) for e in entries]}, default=str)
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

    with get_session() as db:
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


# ---------------------------------------------------------------------------
# Templated resources
# ---------------------------------------------------------------------------

@mcp.resource(
    "shoes://owned/{shoe_id}",
    name="Shoe Detail",
    description="Full detail for a specific owned shoe including stats, recent runs and notes",
    mime_type="application/json",
)
def shoe_detail_resource(shoe_id: int) -> str:
    """Full detail for a specific owned shoe"""
    import json

    with get_session() as db:
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            return f"No shoe found with id {shoe_id}"

        stats = rotation.compute_lifetime_stats(db, shoe.id)
        cost_per_km = rotation.cost_per_km(shoe)
        mileage_limit = shoe.mileage_limit
        bar = _format_mileage_bar(shoe.current_mileage, mileage_limit)
        label = shoe.nickname or ""
        name = f"{shoe.brand} {shoe.model}" + (f" ({label})" if label else "")
        pct = round(shoe.current_mileage / mileage_limit * 100) if mileage_limit else None
        mileage_line = f"{round(shoe.current_mileage)}km / {round(mileage_limit)}km ({pct}%)" if mileage_limit else f"{round(shoe.current_mileage)}km"

        type_line = f" | **Type:** {shoe.shoe_type}" if shoe.shoe_type else ""
        md_lines = [
            f"# {name}",
            f"**Status:** {shoe.status.capitalize()} | **Mileage:** {mileage_line}{type_line}",
        ]
        if shoe.purchase_price:
            md_lines.append(
                f"**Purchase price:** ${shoe.purchase_price:.2f}"
                + (f" | **Cost per km:** ${cost_per_km:.2f}" if cost_per_km else "")
            )
        pace = stats.lifetime_avg_pace or "—"
        hr = f"{stats.lifetime_avg_hr}bpm" if stats.lifetime_avg_hr else "—"
        runs_count = stats.total_runs
        md_lines.append(f"**Lifetime stats:** Avg {pace} · {hr} · {runs_count} runs")

        recent_runs = (
            db.query(ShoeRun)
            .join(Activity, ShoeRun.activity_id == Activity.id)
            .options(contains_eager(ShoeRun.activity))
            .filter(ShoeRun.owned_shoe_id == shoe_id)
            .order_by(desc(Activity.run_date), desc(ShoeRun.created_at))
            .limit(5)
            .all()
        )
        if recent_runs:
            md_lines += ["", "## Recent Runs"]
            for r in recent_runs:
                a = r.activity
                date_str = a.run_date.strftime("%b %d") if a.run_date else "—"
                p = rotation.seconds_to_pace(a.avg_pace_s_per_km) if a.avg_pace_s_per_km else "—"
                h = f"{a.avg_hr}bpm" if a.avg_hr else "—"
                md_lines.append(f"- {date_str} · {a.distance_km:.1f}km · {p} · {h}")

        recent_notes = (
            db.query(ShoeNote)
            .filter(ShoeNote.owned_shoe_id == shoe_id)
            .order_by(desc(ShoeNote.created_at))
            .limit(3)
            .all()
        )
        if recent_notes:
            md_lines += ["", "## Notes"]
            for n in recent_notes:
                km_tag = f"[{round(n.mileage_at_note)}km]" if n.mileage_at_note else ""
                md_lines.append(f"- {km_tag} {n.body}")

        markdown = "\n".join(md_lines)
        payload = json.dumps(
            {
                "shoe": _owned_shoe_to_dict(shoe, stats),
                "recent_runs": [_shoe_run_to_dict(r) for r in recent_runs],
                "recent_notes": [_shoe_note_to_dict(n) for n in recent_notes],
            },
            default=str,
        )
        return f"{markdown}\n\n```json\n{payload}\n```"


# Run-source badges for the run-history resource. Default (manual) covers any
# unrecognized source.
_SOURCE_BADGES = {
    "coros": "🤖 coros",
    "strava": "🟠 strava",
    "manual": "✍ manual",
}


@mcp.resource(
    "shoes://owned/{shoe_id}/runs",
    name="Shoe Run History",
    description="Complete run history for a specific owned shoe",
    mime_type="application/json",
)
def shoe_runs_resource(shoe_id: int) -> str:
    """Complete run history for a specific owned shoe, newest first"""
    import json

    with get_session() as db:
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            return f"No shoe found with id {shoe_id}"

        runs = (
            db.query(ShoeRun)
            .join(Activity, ShoeRun.activity_id == Activity.id)
            .options(contains_eager(ShoeRun.activity))
            .filter(ShoeRun.owned_shoe_id == shoe_id)
            .order_by(desc(Activity.run_date), desc(ShoeRun.created_at))
            .all()
        )
        label = shoe.nickname or ""
        name = f"{shoe.brand} {shoe.model}" + (f" ({label})" if label else "")

        md_lines = [
            f"# Run History — {name}",
            f"_{len(runs)} run{'s' if len(runs) != 1 else ''} logged_",
            "",
            "| Date | Distance | Pace | HR | Source |",
            "|------|----------|------|----|--------|",
        ]
        for r in runs:
            a = r.activity
            date_str = a.run_date.strftime("%b %d, %Y") if a.run_date else "—"
            pace = rotation.seconds_to_pace(a.avg_pace_s_per_km) if a.avg_pace_s_per_km else "—"
            hr = f"{a.avg_hr}bpm" if a.avg_hr else "—"
            source_badge = _SOURCE_BADGES.get(a.source, "✍ manual")
            md_lines.append(f"| {date_str} | {a.distance_km:.1f}km | {pace} | {hr} | {source_badge} |")

        stats = rotation.compute_lifetime_stats(db, shoe_id)
        markdown = "\n".join(md_lines)
        payload = json.dumps(
            {
                "shoe_id": shoe_id,
                "runs": [_shoe_run_to_dict(r) for r in runs],
                "lifetime_avg_pace": stats.lifetime_avg_pace,
                "lifetime_avg_hr": stats.lifetime_avg_hr,
                "total_runs": stats.total_runs,
            },
            default=str,
        )
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "shoes://owned/{shoe_id}/notes",
    name="Shoe Notes Journal",
    description="Timestamped notes journal for a specific owned shoe",
    mime_type="application/json",
)
def shoe_notes_resource(shoe_id: int) -> str:
    """Timestamped notes journal for a specific owned shoe"""
    import json

    with get_session() as db:
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            return f"No shoe found with id {shoe_id}"

        notes = (
            db.query(ShoeNote)
            .filter(ShoeNote.owned_shoe_id == shoe_id)
            .order_by(desc(ShoeNote.created_at))
            .all()
        )
        label = shoe.nickname or ""
        name = f"{shoe.brand} {shoe.model}" + (f" ({label})" if label else "")

        md_lines = [f"# Notes — {name}", ""]
        if not notes:
            md_lines.append("_No notes yet._")
        for n in notes:
            date_str = n.created_at.strftime("%b %d, %Y") if n.created_at else "—"
            km_str = f"{round(n.mileage_at_note)}km" if n.mileage_at_note is not None else ""
            badge = "🏁 checkpoint" if n.triggered_by == "checkpoint" else "✍ manual"
            md_lines.append(f"[{date_str} · {km_str}] {badge}")
            md_lines.append(n.body)
            md_lines.append("")

        markdown = "\n".join(md_lines).rstrip()
        payload = json.dumps({"shoe_id": shoe_id, "notes": [_shoe_note_to_dict(n) for n in notes]}, default=str)
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "shoes://review/{shoe_id}",
    name="Shoe Review",
    description="Stored review draft for a specific owned shoe (R3.3)",
    mime_type="text/plain",
)
def shoe_review_resource(shoe_id: int) -> str:
    """
    Return the stored review draft for an owned shoe, or a prompt to start
    the review workflow if none exists yet.

    Readable from Claude Desktop to retrieve the draft without re-running the
    LLM call. The draft is written by draft_shoe_review (auto-save) and
    overwritten by save_shoe_review (runner-edited).
    """
    with get_session() as db:
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            return f"No shoe found with id {shoe_id}"

        label = shoe.nickname or ""
        name = f"{shoe.brand} {shoe.model}" + (f" ({label})" if label else "")

        if not shoe.review_draft:
            note_count = db.query(ShoeNote).filter(ShoeNote.owned_shoe_id == shoe_id).count()
            note_hint = (
                f" It has {note_count} journal note(s) to draw from."
                if note_count > 0 else " Add some notes first via add_shoe_note."
            )
            return (
                f"# Review — {name}\n\n"
                f"_No review stored yet._{note_hint}\n\n"
                f"Run `draft_shoe_review({shoe_id})` to generate a draft from the notes journal."
            )

        return f"# Review — {name}\n\n{shoe.review_draft}"


@mcp.resource(
    "shoes://deals/{brand}",
    name="Brand Deals",
    description="Active deals filtered by brand name",
    mime_type="application/json",
)
def brand_deals_resource(brand: str) -> str:
    """Active deals for a specific brand, sorted by savings percentage"""
    import json

    with get_session() as db:
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


@mcp.resource(
    "strava://runs/{year}/{month}",
    name="Strava Runs by Month",
    description="Imported Strava runs for a given year/month, so a chat can pull one month without flooding context",
    mime_type="application/json",
)
def strava_runs_by_month_resource(year: str, month: str) -> str:
    """Imported Strava runs for a single month (year/month as YYYY / MM or M)."""
    import json
    from calendar import monthrange
    from datetime import date as _date

    try:
        y, m = int(year), int(month)
        start = _date(y, m, 1)
        end = _date(y, m, monthrange(y, m)[1])
    except (ValueError, TypeError):
        return f"Invalid year/month: {year}/{month} (expected e.g. 2026/07)"

    with get_session() as db:
        runs = (
            db.query(Activity)
            .filter(
                Activity.source == "strava",
                Activity.activity_type == "Run",
                Activity.run_date >= start,
                Activity.run_date <= end,
            )
            .order_by(Activity.run_date)
            .all()
        )

        total_km = round(sum(r.distance_km or 0.0 for r in runs), 1)
        md_lines = [
            f"# Strava Runs — {y}-{m:02d}",
            f"_{len(runs)} run{'s' if len(runs) != 1 else ''} · {total_km}km total_",
            "",
            "| Date | Distance | Pace | HR | Gear |",
            "|------|----------|------|----|------|",
        ]
        run_dicts = []
        for r in runs:
            date_str = r.run_date.strftime("%b %d") if r.run_date else "—"
            pace = rotation.seconds_to_pace(r.avg_pace_s_per_km) if r.avg_pace_s_per_km else "—"
            hr = f"{r.avg_hr}bpm" if r.avg_hr else "—"
            gear = r.gear_name or "—"
            md_lines.append(f"| {date_str} | {r.distance_km:.1f}km | {pace} | {hr} | {gear} |")
            run_dicts.append({
                "strava_activity_id": r.strava_activity_id,
                "run_date": r.run_date.isoformat() if r.run_date else None,
                "distance_km": r.distance_km,
                "avg_pace": pace if pace != "—" else None,
                "avg_hr": r.avg_hr,
                "gear_name": r.gear_name,
                "name": r.name,
            })

        markdown = "\n".join(md_lines)
        payload = json.dumps(
            {"year": y, "month": m, "total_km": total_km, "runs": run_dicts},
            default=str,
        )
        return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "training://summary",
    name="Training Summary",
    description="Last 12 weeks of training volume, pace, HR, and elevation — for chat pre-priming",
    mime_type="application/json",
)
def training_summary_resource() -> str:
    """Last 12 weeks of weekly training data for chat pre-priming."""
    import json
    from datetime import date as _date, timedelta

    today = _date.today()
    date_from = today - timedelta(weeks=12)

    with get_session() as db:
        buckets = strava_stats.training_summary(db, period="weekly", date_from=date_from)

    md_lines = [
        "# Training Summary (last 12 weeks)",
        "",
        "| Week | Distance | Runs | Avg Pace | Avg HR | Elevation |",
        "|------|----------|------|----------|--------|-----------|",
    ]
    for b in buckets:
        pace = b.avg_pace or "—"
        hr = f"{b.avg_hr}bpm" if b.avg_hr else "—"
        elev = f"{round(b.elevation_gain_m)}m" if b.elevation_gain_m else "—"
        md_lines.append(f"| {b.period} | {b.total_km:.1f}km | {b.run_count} | {pace} | {hr} | {elev} |")

    if not buckets:
        md_lines.append("_No runs in the last 12 weeks._")

    markdown = "\n".join(md_lines)
    payload = json.dumps(
        {
            "period": "weekly",
            "date_from": date_from.isoformat(),
            "date_to": today.isoformat(),
            "buckets": [
                {
                    "period": b.period,
                    "total_km": b.total_km,
                    "run_count": b.run_count,
                    "avg_pace": b.avg_pace,
                    "avg_hr": b.avg_hr,
                    "elevation_gain_m": b.elevation_gain_m,
                }
                for b in buckets
            ],
        },
        default=str,
    )
    return f"{markdown}\n\n```json\n{payload}\n```"


@mcp.resource(
    "training://fitness",
    name="Fitness Metrics",
    description="Latest COROS athlete fitness snapshot: VO2 max, threshold pace, race predictions, running level",
    mime_type="application/json",
)
def training_fitness_resource() -> str:
    """Latest athlete fitness snapshot from COROS, for chat pre-priming alongside training://summary."""
    import json

    with get_session() as db:
        snap = fitness_svc.latest(db)

    if snap is None:
        no_data = "# Fitness Metrics\n\n_No fitness data recorded yet. Use the `sync_fitness` prompt to fetch metrics from COROS._"
        return f"{no_data}\n\n```json\n{{\"has_data\": false}}\n```"

    threshold_pace = rotation.seconds_to_pace(snap.threshold_pace_s_per_km) if snap.threshold_pace_s_per_km else None
    captured = snap.captured_at.strftime("%Y-%m-%d") if snap.captured_at else "—"

    md_lines = [f"# Fitness Metrics (as of {captured})", ""]
    if snap.vo2max is not None:
        md_lines.append(f"**VO2 Max:** {snap.vo2max:.1f} ml/kg/min")
    if threshold_pace:
        md_lines.append(f"**Threshold pace:** {threshold_pace}")
    if snap.running_level is not None:
        md_lines.append(f"**Running level:** {snap.running_level:.1f}")

    if snap.race_predictions:
        distance_labels = {
            "5.0": "5k", "10.0": "10k", "21.0975": "Half marathon", "42.195": "Marathon"
        }
        md_lines += ["", "**Race predictions:**", "| Distance | Predicted |", "|----------|-----------|"]
        for dist_str, seconds in sorted(snap.race_predictions.items(), key=lambda x: float(x[0])):
            label = distance_labels.get(dist_str, f"{dist_str} km")
            h, rem = divmod(int(seconds), 3600)
            m, s = divmod(rem, 60)
            time_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            md_lines.append(f"| {label} | {time_str} |")

    markdown = "\n".join(md_lines)
    payload = json.dumps(
        {
            "has_data": True,
            "captured_at": snap.captured_at.isoformat() if snap.captured_at else None,
            "vo2max": snap.vo2max,
            "threshold_pace_s_per_km": snap.threshold_pace_s_per_km,
            "threshold_pace": threshold_pace,
            "running_level": snap.running_level,
            "race_predictions": snap.race_predictions,
        },
        default=str,
    )
    return f"{markdown}\n\n```json\n{payload}\n```"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@mcp.prompt()
def sync_coros_runs(days_back: int = 2) -> str:
    """
    Sync recent COROS runs and assign them to shoes in your rotation.
    Fetches unsynced runs, suggests shoe assignments based on pace
    and distance, and logs confirmed runs after your review.
    """
    return f"""# COROS Sync Agent

You are acting as a COROS run sync agent for the Running Shoe Deal
Finder app. Follow this exact process.

## Step 1 — Fetch recent runs from COROS
Call querySportRecords with:
- sportTypeCodes: [100, 101, 102, 103] (all running types)
- pageSize: 20
- pageIndex: 1
- timezone: America/Toronto

This uses the COROS MCP connector directly — do NOT call 
fetch_unsynced_coros_runs as it requires API credentials 
that are not configured.

## Step 1b — Check what's already logged
Call get_shoe_runs for each active owned shoe to get recently 
logged runs. Use run_date and distance_km to identify which 
COROS activities have already been logged (match by date and 
distance within 0.1km tolerance). Exclude already-logged runs 
from the sync queue.

## Step 2 — Get current rotation
Call get_owned_shoes to see all active shoes with their shoe_type
and current mileage.

## Step 3 — Suggest shoe assignment for each run
For each unsynced run, reason about the best shoe match using BOTH
signals below — do not rely on pace alone.

### Pace signal (primary)
- < 3:30/km → favors short_distance_racer or intervals
- 3:30–4:15/km → favors tempo long_distance_racer or tempo
- 4:00–4:30/km → favors long_run
- 4:30–5:30/km → favors daily_trainer
- > 5:30/km → favors recovery or daily_trainer

### Distance signal (secondary, refines the pace signal)
- < 5km → favors intervals or short_distance_racer
- 5–16km → favors daily_trainer
- 16–22km → favors tempo or daily_trainer
- > 21km → favors long_run or long_distance_racer

### Resolution
- If pace and distance signals agree on a shoe_type, that's the
  suggestion.
- If they conflict, pick the shoe_type with an active shoe in the
  rotation, preferring the one with lower current mileage.
- Only suggest shoes that are status=active. Never suggest a
  retired shoe.
- If multiple active shoes share the matched shoe_type, suggest
  the one with lower mileage (spread wear more evenly).
- If no shoe in the rotation matches the inferred shoe_type, say so
  explicitly rather than forcing a bad match.

## Step 4 — Present all suggestions together
Show every unsynced run with its suggested shoe and a brief reason,
in a single structured response.

Format:
"Here are my suggestions for [N] unsynced runs:

[Date] · [distance]km · [pace]/km · [hr]bpm
→ [Brand Model] ([shoe_type], [current_mileage]km)
Reason: [one short sentence]

...repeat for each run...

Confirm all, adjust specific runs, or skip any?"

## Step 5 — Wait for user confirmation
Do not log anything until the user responds. Accept any natural
language mix of confirmations, changes, and skips. If ambiguous,
ask for clarification.

## Step 6 — Fetch rich per-run detail then log confirmed runs

For EACH confirmed run you MUST call getActivityDetail before confirm_coros_run.
Do NOT skip this call — querySportRecords does not return these fields.

  Call `getActivityDetail(labelId=<coros_activity_id>, sportType=<sport_type>)`

  Extract from the response:
  - name            → activity name/label the runner set in COROS
  - elevation_gain_m → totalAscent (metres)
  - moving_time_s   → movingTime (seconds)
  - elapsed_time_s  → totalTime (seconds)
  - avg_cadence     → avgCadence
  - calories        → calorie
  - training_load   → trainingLoad
  - training_focus  → coachingZoneLabel or equivalent coaching label

  All fields are optional. If getActivityDetail fails or a field is absent, omit it.

Then, using the name and training_focus from getActivityDetail, infer an
activity_tag suggestion (first match wins — the order is precedence):
  "parkrun" → Parkrun · "interval"/"repeat" → Intervals · "track" → Track ·
  "tempo"/"threshold" → Tempo · "long run"/"long" → Long Run · "trail" → Trail ·
  "race"/"marathon" → Race · "recovery"/"easy"/"jog" → Easy · else untagged.
If a tag is suggested, ask the runner to confirm or override before logging —
e.g. "COROS name 'Tempo 8k' → tag `Tempo`? (y/n)". The full vocabulary is
Easy, Long Run, Recovery, Tempo, Intervals, Track, Workout, Trail, Parkrun, Race.
Never apply a tag without confirmation (C9). Omit the tag entirely if unconfirmed.

Then call confirm_coros_run with:
- coros_activity_id (from querySportRecords)
- owned_shoe_id (the confirmed shoe)
- date, distance_km, avg_pace, avg_hr from querySportRecords data
- All fields extracted from getActivityDetail above

## Step 7 — Summarise results
"Logged [N] runs:
- [Shoe name]: +[total km added]km (now [new total]km)
...
[Skipped: N runs]"

## Step 8 — Proactive threshold check
For any shoe that crossed 600km, 700km, or 800km, flag it and offer
to check replacement deals or add a note.

## General rules
- Never log a run without explicit user confirmation
- Never invent data — basic fields (date, distance, pace, HR) come from
  querySportRecords (Step 1); rich fields (name, elevation, times, cadence,
  calories, load, focus) come from getActivityDetail (Step 6)
- If confirm_coros_run returns success: false for any run, report
  the specific error and continue processing the rest
- Keep the tone direct and concise — this user is a competitive
  runner who wants clear information, not chattiness
"""


@mcp.prompt()
def sync_fitness() -> str:
    """
    Sync COROS athlete fitness metrics (VO2 max, threshold pace, race
    predictions, running level) into Anton's Training tab fitness card.
    Fetches the latest snapshot from COROS, confirms with the runner,
    then records it via record_athlete_metrics.
    """
    return """# COROS Fitness Sync Agent

You are syncing athlete-level fitness metrics from COROS into Anton.
Follow this exact process.

## Step 1 — Fetch fitness assessment from COROS
Call `queryFitnessAssessmentOverview` from the COROS MCP connector.
This returns VO2 max, lactate-threshold pace, race predictions, and
running level. Do NOT call record_athlete_metrics yet.

## Step 2 — Present the fetched values for confirmation (C9)
Show every metric you received in a clear table, e.g.:

"COROS reports the following fitness metrics — confirm to record?

| Metric | Value |
|--------|-------|
| VO2 Max | 62.0 ml/kg/min |
| Threshold pace | 3:45/km (225 s/km) |
| Running level | 74.5 |
| Race predictions | 5k: 19:15 · 10k: 40:00 · HM: 1:28:30 · Marathon: 3:03:00 |

Record this snapshot? (yes/no)"

Convert threshold pace to seconds/km for storage (e.g. 3:45/km → 225).
Convert race prediction times to seconds for storage.
Format race_predictions as {"5.0": <s>, "10.0": <s>, "21.0975": <s>, "42.195": <s>}.
Include only distances the COROS response actually provides.

## Step 3 — Wait for runner confirmation
Do NOT call record_athlete_metrics until the runner says yes (or equivalent).
If the runner corrects a value, use the corrected version.

## Step 4 — Record the confirmed snapshot
Call record_athlete_metrics with the confirmed values:
- vo2max (Float, ml/kg/min)
- threshold_pace_s_per_km (Integer, seconds/km)
- race_predictions (dict, distance string → seconds Integer)
- running_level (Float)

## Step 5 — Confirm success
"Fitness snapshot recorded (captured_at: <timestamp>). The Training tab
fitness card will now show the updated metrics."

## General rules
- Never record metrics without explicit runner confirmation (C9)
- Never invent or extrapolate values not present in the COROS response
- If queryFitnessAssessmentOverview fails or returns no data, say so and stop
- Keep the tone direct and concise
"""


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

    The high-water mark (AppSettings key "last_deal_alert_check_at") is updated
    on every call; subsequent calls report only incremental events.

    Use this to answer "any new deals since yesterday?" or before presenting
    the deal_alert_digest prompt for a structured briefing. Read-only with
    respect to deals — the only write is the settings high-water mark.
    """
    with get_session() as db:
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
            "new_deals": a.new_deals,
        }

    return {
        "since": digest.since,
        "checked_at": digest.checked_at,
        "first_run": digest.first_run,
        "has_alerts": digest.has_alerts,
        "new_deals": [_new_deal_to_dict(a) for a in digest.new_deals],
        "price_drops": [_drop_to_dict(a) for a in digest.price_drops],
        "replacement_alerts": [_replacement_to_dict(a) for a in digest.replacement_alerts],
    }


@mcp.prompt()
def weekly_rotation_summary() -> str:
    """
    Generate the runner's weekly rotation digest — volume vs last week,
    per-shoe usage, retirement pipeline, notable runs, 100km checkpoints,
    and next-race countdown. Read-only; no confirmation or writes needed.
    Typically run on Mondays to review the previous week.
    """
    return """# Weekly Rotation Summary

You are composing the runner's weekly training and rotation digest.
This is READ-ONLY — no writes, no confirmation gates.

## Step 1 — Fetch the weekly snapshot
Call `get_weekly_summary()`. It returns a single structured object covering
the current ISO week (Monday through Sunday): volume, per-shoe usage,
retirement pipeline, notable runs, 100km checkpoints, and next race.

## Step 2 — Compose and present the digest
Use this exact structure. Omit any section whose data list is empty.

---
**Week of [week_start] – [week_end]**

**Volume:** [this_week_km] km
[If last_week_km > 0: "(↑ [delta_km] km vs [last_week_km] km last week)" if delta_km > 0,
 else "(↓ [|delta_km|] km vs [last_week_km] km last week)" if delta_km < 0,
 else "(= same as last week's [last_week_km] km)"]
[If last_week_km == 0 and this_week_km > 0: "(no runs last week)"]

**Shoes used this week:**
[For each entry in per_shoe_usage, most-used first:]
- [Brand] [Model][" (nickname)" if nickname] — [km_this_week] km · [run_count] run(s)[" · " + shoe_type if shoe_type]

**Retirement pipeline — [count] shoe(s) at ≥ 75% of limit:**
[For each entry in pipeline, worst-first:]
- [Brand] [Model][" (nickname)" if nickname] — [current_mileage] km / [mileage_limit] km ([pct×100 rounded to 0dp]%)[" · " + replacement_deals + " replacement deal(s) available" if replacement_deals > 0]

**Notable runs:**
[For each entry in notable_runs, newest-first:]
- [run_date] · [activity_tag] · [distance_km] km @ [avg_pace or —][ · avg_hr bpm if avg_hr set][ · shoe label if shoe set][ · name if name set]

**Checkpoints this week:**
[For each entry in checkpoints_this_week:]
- [Brand] [Model] crossed [checkpoint_km] km ([triggered_at])

**Next race:** [If next_race:
[name] — [race_date] ([days_remaining] day(s) / [weeks_remaining] week(s) away)[", target " + target_pace if target_pace]
Else: "No upcoming races scheduled."]
---

## Rules
- Never invent data not present in get_weekly_summary's response
- If per_shoe_usage is empty: state "No attributed runs this week"
- Pipeline pct display: multiply by 100 and round to the nearest whole number
  (e.g. 0.8234 → 82%) — never show raw fractions
- delta_km direction: positive means more volume this week (↑), negative means less (↓)
- Keep the tone informative and direct; no cheerleading ("Great job!" etc.)
- Do not add observations not grounded in the data (no invented training advice)
"""


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


@mcp.tool()
def get_race_block_context(weeks_back: int = 12) -> dict:
    """
    Compile the race-block training context for the advisor prompt (R3.6).

    Returns a structured snapshot covering:
    - Next upcoming race: name, date, distance, days/weeks to race, target pace.
    - Recent weekly volumes: last `weeks_back` weeks of km, run count, avg pace,
      avg HR — newest first. Used to assess whether current volume is on track
      for the goal race.
    - Retirement pipeline: active shoes at ≥ 75% of their mileage limit.
      Includes shoe_type so you can flag race-shoe wear concerns specifically.
    - Latest fitness snapshot: VO2 max, lactate-threshold pace (as "M:SS/km"),
      race predictions, and running level from COROS (if ever synced).

    This is read-only — no writes, no confirmation gate needed.
    Call this before running the race_block_advisor prompt.

    Args:
        weeks_back: Number of recent weekly buckets to include (default 12, max 52).
    """
    weeks_back = max(1, min(weeks_back, 52))
    with get_session() as db:
        ctx = race_advisor_svc.race_block_context(db, weeks_back=weeks_back)

    result: dict = {
        "has_next_race": ctx.has_next_race,
        "next_race": None,
        "recent_weeks": [
            {
                "period": w.period,
                "total_km": w.total_km,
                "run_count": w.run_count,
                "avg_pace": w.avg_pace,
                "avg_hr": w.avg_hr,
            }
            for w in ctx.recent_weeks
        ],
        "avg_weekly_km": ctx.avg_weekly_km,
        "pipeline": [
            {
                "shoe_id": p.shoe_id,
                "brand": p.brand,
                "model": p.model,
                "nickname": p.nickname,
                "shoe_type": p.shoe_type,
                "pct": p.pct,
                "current_mileage": p.current_mileage,
                "mileage_limit": p.mileage_limit,
                "replacement_deals": p.replacement_deals,
            }
            for p in ctx.pipeline
        ],
        "has_fitness": ctx.has_fitness,
        "fitness": None,
    }

    if ctx.next_race:
        r = ctx.next_race
        result["next_race"] = {
            "name": r.name,
            "race_date": r.race_date,
            "distance_km": r.distance_km,
            "days_to_race": r.days_to_race,
            "weeks_to_race": r.weeks_to_race,
            "target_pace": r.target_pace,
            "target_time_s": r.target_time_s,
        }

    if ctx.fitness:
        f = ctx.fitness
        result["fitness"] = {
            "vo2max": f.vo2max,
            "threshold_pace": f.threshold_pace,
            "race_predictions": f.race_predictions,
            "running_level": f.running_level,
            "captured_at": f.captured_at,
        }

    return result


@mcp.prompt()
def race_block_advisor() -> str:
    """
    Generate race-block training observations for the runner's current goal race.

    Reads the race countdown, recent weekly volumes, rotation state, and fitness
    metrics to produce block-level observations — where the runner stands now,
    what the volume trend implies, and any rotation concerns for race day.
    Advisory observations only; no detailed training plan generation.
    Read-only — no writes, no confirmation gate.
    """
    return """# Race-Block Training Advisor

You are producing training-block observations for a competitive runner.
This is READ-ONLY — no writes, no confirmation gates. Advisory only.

## Step 1 — Fetch the context
Call `get_race_block_context()`. It returns the next race, recent weekly
volumes, rotation pipeline state, and latest fitness metrics.

## Step 2 — Produce the advisory

Use the structure below. Omit any section whose data is absent.

---
**Race-Block Summary**

### Goal Race
[If has_next_race:]
**[next_race.name]** — [next_race.race_date]
[days_to_race] days / [weeks_to_race] weeks out[", [next_race.distance_km] km" if distance_km set]
[If target_pace: "Target pace: [target_pace]"]
[Else if no race: "No upcoming races scheduled — observations are general."]

### Volume (last [count of recent_weeks] weeks)
Average: [avg_weekly_km] km/week

[List recent_weeks newest-first, one line each:]
[period] — [total_km] km · [run_count] run(s)[" · " + avg_pace if avg_pace]

**Trend observation:**
[Compare the most recent 2–3 weeks against the 12-week average. Examples:]
- If recent weeks are well above average: "Volume is above the block average — monitor fatigue
  and ensure adequate recovery before [race name]."
- If recent weeks are declining: "Volume has dropped vs the block average. If intentional
  (taper), this is appropriate at [weeks_to_race] weeks out; otherwise worth checking."
- If stable: "Volume is consistent with the block average."
[If has_next_race and weeks_to_race ≤ 3: "At [weeks_to_race] week(s) out, taper should be underway."]
[If has_next_race and weeks_to_race is between 4 and 8: "In the race-specific phase — quality over
 quantity; key workouts at target pace matter more than peak volume."]
[If has_next_race and weeks_to_race > 8: "Still in the base-building window — volume consistency
 is the priority."]

### Rotation
[If pipeline is non-empty:]
[For each shoe in pipeline:]
- **[brand] [model]**[" ([nickname])" if nickname] — [pct×100 rounded to 0dp]%
  of limit ([current_mileage]/[mileage_limit] km)[", type: " + shoe_type if shoe_type]
  [If shoe_type and "Race" in shoe_type and has_next_race:
   "Race shoe at this mileage — consider the replacement timeline vs race day."]
  [If replacement_deals > 0: "[replacement_deals] replacement deal(s) available."]
[Else: "No shoes in the retirement pipeline."]

### Fitness
[If has_fitness:]
VO2 Max: [vo2max if set, else "—"] · Threshold pace: [threshold_pace if set, else "—"]
[If running_level: "Running level: [running_level]"]
[If race_predictions and has_next_race and next_race.distance_km set:]
  [Find the closest distance key in race_predictions to next_race.distance_km:]
  Predicted time at [distance_km] km: [format total_s as H:MM:SS or M:SS depending on length]
[If threshold_pace and has_next_race and next_race.target_pace:
  Compare threshold_pace and target_pace: note if target pace is faster or slower than threshold.
  E.g.: "Target pace ([target_pace]) is [X sec/km] faster than threshold ([threshold_pace]) —
  a demanding goal requiring sustained anaerobic contribution."]
[Else if has_next_race and not has_fitness: "No fitness snapshot on record — sync COROS via
 the sync_fitness prompt for VO2 max and race predictions."]

---

## Rules
- Never invent data not present in get_race_block_context's response
- Volume trend: compare the two most recent non-zero weeks to avg_weekly_km
  (a single anomalous week isn't a trend)
- pct display: multiply by 100 and round to the nearest whole number
- Keep observations concrete and grounded in the numbers; no cheerleading
- Do not generate a full training plan — point out where the runner stands and
  flag concerns; the runner decides what to do with them
- If weeks_to_race ≤ 0, the race is today or in the past — note that and pivot
  to "next goal race" framing if another race exists
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
    with get_session() as db:
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
    with get_session() as db:
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
