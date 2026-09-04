"""
One-off admin/maintenance endpoints — not part of the regular app flow.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Deal, PriceRecord, ScrapeRun
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.lock import force_release_scrape_lock, is_scrape_running
from app.services import schedule as schedule_svc

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/scrape-lock/release", response_model=dict)
def release_scrape_lock_endpoint():
    """
    Force-release the process-wide scrape lock. No-op if no scrape holds it;
    releases it if one does. Returns {"was_held": bool}.

    The operational escape hatch for a wedged lock (M3): the background scrape
    job now releases the lock in a finally that covers its whole body, so a
    wedge should no longer happen — but this endpoint stays as the recovery
    door of last resort short of a process restart.

    Auth: gated behind the shared bearer token by the app-wide auth middleware
    (R2.1, app/middleware/auth.py) like every other mutation surface — an
    unauthenticated call gets 401 (asserted in tests/test_auth.py).
    """
    return {"was_held": force_release_scrape_lock()}


@router.post("/cleanup-kids-shoes", response_model=dict)
def cleanup_kids_shoes(db: Session = Depends(get_db)):
    """
    One-time cleanup for price_records/deals scraped before the kids/junior
    filter (BaseScraper.search_products_filtered) existed. Run once after
    deploying that filter; safe to re-run (no-ops once everything's clean).

    Neither table stores the scraped product's name/title — only
    product_url survives long-term, and for every scraper here that's a
    slug derived from the retailer's own product title/options (e.g.
    ".../adidas-kids-runner-gs"), so that's matched against the same
    keyword filter as a best-effort proxy for "product name."
    """
    bad_records = [
        r for r in db.query(PriceRecord).all() if BaseScraper.is_kids_shoe(r.product_url)
    ]
    bad_deals = [
        d for d in db.query(Deal).all() if BaseScraper.is_kids_shoe(d.product_url)
    ]

    for d in bad_deals:
        db.delete(d)
    for r in bad_records:
        db.delete(r)
    db.commit()

    return {
        "removed_price_records": len(bad_records),
        "removed_deals": len(bad_deals),
    }


def _schedule_response(db: Session) -> dict:
    """
    Shared body for the schedule GET/PUT: resolved status + is_scraping_now +
    the five most recent scheduled runs. GET and PUT return the identical shape
    so the frontend can consume a PUT response directly to refresh its cache.
    """
    status = schedule_svc.get_status(db)

    recent = (
        db.query(ScrapeRun)
        .filter(ScrapeRun.trigger == "scheduled")
        .order_by(ScrapeRun.started_at.desc())
        .limit(5)
        .all()
    )

    return {
        **status,
        "is_scraping_now": is_scrape_running(),
        "recent_scheduled_runs": [
            {
                "id": r.id,
                "retailer_id": r.retailer_id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "shoes_scraped": r.shoes_scraped,
                "products_found": r.products_found,
                "deals_found": r.deals_found,
                "error": r.error,
            }
            for r in recent
        ],
    }


@router.get("/schedule", response_model=dict)
def get_schedule_status(db: Session = Depends(get_db)):
    """
    Current state of the nightly scrape schedule (R4.1; UI-configurable #7).

    Returns the resolved configuration (enabled, cron, applied_cron, next fire
    time, per-field source), whether a scrape is running right now, and the five
    most recent scheduled-trigger runs from scrape_runs for health-at-a-glance.
    """
    return _schedule_response(db)
