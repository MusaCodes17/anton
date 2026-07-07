"""
One-off admin/maintenance endpoints — not part of the regular app flow.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Deal, PriceRecord
from app.scrapers.base_scraper import BaseScraper
from app.scrapers.lock import force_release_scrape_lock

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

    Auth note: intentionally unauthenticated *for now*, consistent with the
    rest of the API under design_decisions E1. The security pass (R2.1) will
    gate it behind the shared bearer token like every other mutation surface —
    see SECURITY_PASS_PLAN.md §4 (task 8).
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
