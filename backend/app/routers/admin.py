"""
One-off admin/maintenance endpoints — not part of the regular app flow.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Deal, PriceRecord
from app.scrapers.base_scraper import BaseScraper

router = APIRouter(prefix="/admin", tags=["admin"])


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
