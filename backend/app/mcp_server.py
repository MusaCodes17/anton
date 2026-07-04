"""
MCP server exposing this app's core functionality as tools for LLM clients.

Mounted onto the FastAPI app (see app/main.py) at /mcp via
mcp.streamable_http_app(), using Streamable HTTP transport.

Tools stay thin on purpose: they read the same SQLAlchemy models and call
the same ScraperManager the REST routers (app/routers/*.py) use, so there is
exactly one place business logic lives. Each tool opens its own DB session
(FastMCP tools aren't FastAPI route handlers, so they can't use
Depends(get_db)) and closes it when done, mirroring get_db's lifecycle.
"""
from contextlib import contextmanager
from typing import List, Optional

from mcp import types as mcp_types
from mcp.server.fastmcp import FastMCP, Context
from sqlalchemy import desc, func

from datetime import date as date_type, datetime, timezone

from app.coros_client import get_coros_config
from app.database import SessionLocal
from app.models.models import Activity, Deal, OwnedShoe, PriceRecord, Retailer, Shoe, ShoeNote, ShoeRun
from app.scrapers.scraper_manager import ScraperManager, ScrapeInProgressError, scrape_guard
from app.services import rotation, coros as coros_svc, settings as settings_svc, strava_stats, races as races_svc

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
        query = db.query(Deal).filter(Deal.is_active == True)
        if min_savings_percent is not None:
            query = query.filter(Deal.savings_percent >= min_savings_percent)
        needs_shoe_join = brand or shoe_type
        if needs_shoe_join:
            query = query.join(Deal.shoe)
            if brand:
                query = query.filter(Shoe.brand.ilike(f"%{brand}%"))
            if shoe_type:
                query = query.filter(Shoe.shoe_type == shoe_type)
        query = query.order_by(desc(Deal.savings_percent))

        if size:
            # sizes_available is a JSON list column — there's no portable
            # SQLite "contains" filter for it, so overfetch and filter in
            # Python (same approach the Deals page uses client-side).
            deals = [
                d for d in query.limit(limit * 5).all()
                if size in (d.sizes_available or [])
            ][:limit]
        else:
            deals = query.limit(limit).all()

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
        deals = (
            db.query(Deal)
            .join(Deal.shoe)
            .filter(
                Deal.is_active == True,
                Shoe.brand.ilike(f"%{brand}%"),
                Shoe.model.ilike(f"%{model}%"),
            )
            .order_by(desc(Deal.savings_percent))
            .all()
        )
        return [_deal_to_dict(d) for d in deals]


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
def add_shoe(brand: str, model: str, target_price: float, msrp: Optional[float] = None) -> dict:
    """
    Start tracking a new shoe for deals.

    The shoe is tracked across ALL sizes (sizing is handled per-deal, not
    per-shoe), so don't include a size in the model name. This only adds
    the shoe to the database — call trigger_scrape afterward to actually
    search retailers for it.

    Args:
        brand: Shoe brand, e.g. "Nike".
        model: Shoe model, e.g. "Vaporfly 3" (no size).
        target_price: The price (CAD) you want to pay — a deal is created
            once a retailer marks it down to at or below this price.
        msrp: Optional manufacturer's list/retail price, shown alongside
            target_price in the UI so the two aren't confused.
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
async def trigger_scrape(ctx: Context, shoe_id: Optional[int] = None) -> dict:
    """
    Scrape retailers for current prices and detect new deals.

    Scrapes one shoe if shoe_id is given, otherwise every actively-tracked
    shoe across every enabled retailer — which can take a while (it's a
    real, synchronous scrape of live retailer sites, not a queued job).
    Calls the same ScraperManager the REST API's /api/scrape endpoints use.
    If a scrape is already running (from this tool, the REST API, or the
    UI), returns success=False immediately rather than starting another
    one on top of it — do not just retry in a loop; wait and check
    get_dashboard_stats' last_scrape instead.

    Args:
        shoe_id: ID of a specific shoe to scrape (from get_shoes). Omit to
            scrape every active shoe.
    """
    with get_session() as db:
        manager = ScraperManager(db)
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
    """
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
        return {
            "success": True,
            "shoe": f"{shoe.brand} {shoe.model}",
            "mileage": round(shoe.current_mileage, 1),
            "review_draft": review_text,
            "note": "This is a draft — edit before posting.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Connected client does not support sampling. Try this tool from Claude Desktop. ({e})",
        }


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
    """
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
            return {
                "success": True,
                "shoe": f"{shoe.brand} {shoe.model}",
                "final_mileage": round(shoe.current_mileage, 2),
            }
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
        bests = strava_stats.personal_bests(db)
        return {
            "note": "Whole-activity average-pace bests within a distance tolerance, not segment PBs.",
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
                }
                for b in bests
            ],
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

## Step 6 — Log confirmed runs
For each confirmed run call confirm_coros_run with:
- coros_activity_id (from querySportRecords)
- owned_shoe_id (the confirmed shoe)
- date, distance_km, avg_pace, avg_hr from COROS data

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
- Never invent data — all run details come from
  querySportRecords (Step 1)
- If confirm_coros_run returns success: false for any run, report
  the specific error and continue processing the rest
- Keep the tone direct and concise — this user is a competitive
  runner who wants clear information, not chattiness
"""
