"""
Background, concurrent (per-retailer) scrape job — the new flow behind
POST /api/scrape/all. Publishes progress to app.scrape_state for
GET /api/scrape/stream to relay as SSE.

The existing synchronous ScrapeOrchestrator.scrape_shoe/scrape_all_shoes (used
by /api/scrape/shoe/{id}, /api/scrape/retailer/{id}, the MCP trigger_scrape
tool, and the chat assistant) are untouched — this is an additional, parallel
code path that reuses the same per-(shoe, retailer) primitive
(_scrape_retailer_for_shoe) rather than duplicating its logic.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from app.database import SessionLocal
from app.models.models import Retailer, Shoe
from app.scrape_state import scrape_state
from app.scrapers.orchestrator import ScrapeOrchestrator
from app.scrapers.lock import release_scrape_lock

logger = logging.getLogger(__name__)


def _scrape_one_retailer(retailer_id: int, shoe_ids: List[int]) -> dict:
    """
    Runs inside a worker thread (via asyncio.to_thread) — SQLAlchemy
    sessions aren't safe to share across threads, so this opens and closes
    its own, independent of whatever session the caller used to look up
    `retailer_id`/`shoe_ids` in the first place.
    """
    db = SessionLocal()
    try:
        manager = ScrapeOrchestrator(db)
        retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()
        if not retailer:
            return {"deals_found": 0, "errors": [f"Retailer {retailer_id} not found"]}

        shoes = db.query(Shoe).filter(Shoe.id.in_(shoe_ids)).all()

        # scrape_retailer records the ScrapeRun observability row (R2.5),
        # stamps last_scraped_at to the run's finish time (matching the
        # retailer_done event's timestamp below), and commits — this thread
        # owns its own session, so all that persistence happens here.
        result = manager.scrape_retailer(retailer, shoes, trigger="background")
        return {"deals_found": result["deals_found"], "errors": result["errors"]}
    finally:
        db.close()


async def run_scrape_job(retailer_ids: Optional[List[int]] = None) -> None:
    """
    The caller (POST /api/scrape/all) has already synchronously acquired
    the shared scrape lock (try_acquire_scrape_lock) before scheduling this
    as a BackgroundTask — this function owns releasing it, in `finally`,
    along with resetting scrape_state.is_running, so both always happen
    exactly once no matter how this exits.

    The entire body runs under that lock-releasing `finally` (M3 fix,
    2026-07-07): the setup block below (shoe/retailer queries, promo
    detection) used to sit *before* the try, so an exception there would exit
    with the lock still held and wedge every subsequent scrape until a process
    restart. Now any failure after acquisition still releases the lock.
    """
    try:
        db = SessionLocal()
        try:
            shoe_ids = [s.id for s in db.query(Shoe).filter(Shoe.is_active == True).all()]
            query = db.query(Retailer).filter(
                Retailer.is_active == True, Retailer.scraping_enabled == True
            )
            if retailer_ids:
                query = query.filter(Retailer.id.in_(retailer_ids))
            retailers = [(r.id, r.name) for r in query.all()]

            # Site-wide discount codes, same as the old synchronous flow — quick
            # and sequential; not part of the SSE event schema, so no event for it.
            try:
                ScrapeOrchestrator(db).detect_all_promo_codes()
            except Exception as e:
                logger.warning(f"Promo detection failed during background scrape: {e}")
        finally:
            db.close()

        scrape_state.start()

        await scrape_state.publish(
            {"type": "started", "retailers": [name for _, name in retailers]}
        )

        async def run_one(retailer_id: int, name: str) -> dict:
            try:
                # Each retailer's full shoe list scrapes sequentially within
                # its own thread (politeness/rate-limiting + per-scraper
                # instance state like Algolia credential caching depend on
                # that); retailers run concurrently with each other via gather.
                result = await asyncio.to_thread(_scrape_one_retailer, retailer_id, shoe_ids)
                await scrape_state.publish({
                    "type": "retailer_done",
                    "retailer": name,
                    "deals_found": result["deals_found"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return result
            except Exception as e:
                logger.error(f"Retailer scrape failed for {name}: {e}")
                await scrape_state.publish({
                    "type": "retailer_error",
                    "retailer": name,
                    "error": str(e),
                })
                return {"deals_found": 0, "errors": [str(e)]}

        gathered = await asyncio.gather(*[run_one(rid, name) for rid, name in retailers])
        total_deals = sum(r.get("deals_found", 0) for r in gathered)

        completed_at = datetime.now(timezone.utc).isoformat()
        scrape_state.finish(completed_at)
        await scrape_state.publish({
            "type": "completed",
            "total_deals": total_deals,
            "completed_at": completed_at,
        })
    finally:
        # Defensive — guarantees is_running/lock are always cleared even if
        # something above raised before reaching the success path (each
        # run_one already catches its own errors, so gather itself
        # shouldn't raise, but this finally costs nothing and removes any
        # chance of the lock getting stuck held).
        if scrape_state.is_running:
            scrape_state.finish()
        release_scrape_lock()
