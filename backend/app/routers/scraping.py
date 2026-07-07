"""
API routes for scraping operations
"""
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
from typing import Optional, List

from app.database import get_db
from app.models import ScrapeRequest, ScrapeResult
from app.scrape_runner import run_scrape_job
from app.scrape_state import scrape_state
from app.scrapers.orchestrator import ScrapeOrchestrator
from app.scrapers.lock import (
    ScrapeInProgressError,
    scrape_guard,
    try_acquire_scrape_lock,
)
from datetime import datetime

router = APIRouter(prefix="/scrape", tags=["scraping"])


@router.post("/shoe/{shoe_id}", response_model=dict)
def scrape_shoe(
    shoe_id: int,
    retailer_ids: Optional[List[int]] = None,
    db: Session = Depends(get_db)
):
    """
    Manually trigger scraping for a specific shoe
    
    - **shoe_id**: ID of the shoe to scrape
    - **retailer_ids**: Optional list of retailer IDs (if None, scrape all active retailers)
    """
    manager = ScrapeOrchestrator(db)

    try:
        with scrape_guard():
            results = manager.scrape_shoe(shoe_id, retailer_ids)

        if not results.get('success', True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=results.get('error', 'Unknown error')
            )

        return {
            "success": True,
            "message": f"Scraping completed for shoe ID {shoe_id}",
            "results": results,
            "scraped_at": datetime.utcnow().isoformat()
        }

    except ScrapeInProgressError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scraping failed: {str(e)}"
        )


@router.post("/all", response_model=dict)
async def scrape_all_shoes(
    background_tasks: BackgroundTasks,
    retailer_ids: Optional[List[int]] = None,
):
    """
    Kick off a background scrape of all active shoes across every enabled
    retailer (concurrently, per retailer) and return immediately — this no
    longer blocks for the 20-30+ minutes a full catalog can take. Subscribe
    to GET /scrape/stream for live progress; it ends with a "completed" event.

    Returns {"started": false, "reason": "..."} instead of queuing a second
    job if one (of any kind — this or /scrape/shoe/{id} or
    /scrape/retailer/{id}) is already running.

    - **retailer_ids**: Optional list of retailer IDs (if None, scrape all active retailers)
    """
    if not try_acquire_scrape_lock():
        return {"started": False, "reason": "Scrape already in progress"}

    background_tasks.add_task(run_scrape_job, retailer_ids)
    return {"started": True}


@router.get("/stream")
async def scrape_stream():
    """
    SSE stream of progress for the current (or most recently finished)
    background scrape job kicked off by POST /scrape/all. Event types:
        {"type": "started", "retailers": [...]}
        {"type": "retailer_done", "retailer": "...", "deals_found": N, "timestamp": "..."}
        {"type": "retailer_error", "retailer": "...", "error": "..."}
        {"type": "completed", "total_deals": N, "completed_at": "..."}

    Connecting after a job already finished replays its full history
    (ending in "completed") instead of hanging; connecting when nothing has
    ever run just closes immediately.
    """
    queue = scrape_state.subscribe()

    async def event_generator():
        try:
            if queue.empty() and not scrape_state.is_running:
                return  # nothing has ever run and nothing is running now
            while True:
                event = await queue.get()
                yield {"event": "message", "data": json.dumps(event)}
                if event.get("type") == "completed":
                    break
        finally:
            scrape_state.unsubscribe(queue)

    return EventSourceResponse(event_generator())


@router.post("/retailer/{retailer_id}", response_model=dict)
def scrape_retailer(
    retailer_id: int,
    shoe_ids: Optional[List[int]] = None,
    db: Session = Depends(get_db)
):
    """
    Scrape a specific retailer for all shoes (or specific shoes)
    
    - **retailer_id**: ID of the retailer to scrape
    - **shoe_ids**: Optional list of shoe IDs (if None, scrape all active shoes)
    """
    from app.models.models import Shoe
    
    manager = ScrapeOrchestrator(db)
    
    # Get shoes to scrape
    query = db.query(Shoe).filter(Shoe.is_active == True)
    if shoe_ids:
        query = query.filter(Shoe.id.in_(shoe_ids))
    
    shoes = query.all()
    
    if not shoes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active shoes found"
        )
    
    aggregated_results = {
        'total_shoes': len(shoes),
        'total_products_found': 0,
        'total_prices_recorded': 0,
        'total_deals_found': 0,
        'errors': []
    }

    try:
        with scrape_guard():
            for shoe in shoes:
                results = manager.scrape_shoe(shoe.id, [retailer_id])

                aggregated_results['total_products_found'] += results.get('products_found', 0)
                aggregated_results['total_prices_recorded'] += results.get('prices_recorded', 0)
                aggregated_results['total_deals_found'] += results.get('deals_found', 0)

                if results.get('errors'):
                    aggregated_results['errors'].extend(results['errors'])
    except ScrapeInProgressError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return {
        "success": True,
        "message": f"Scraping completed for retailer ID {retailer_id}",
        "results": aggregated_results,
        "scraped_at": datetime.utcnow().isoformat()
    }


@router.post("/promos", response_model=dict)
def detect_all_promos(db: Session = Depends(get_db)):
    """
    Scan all active retailers' sites for discount codes.
    """
    manager = ScrapeOrchestrator(db)
    try:
        results = manager.detect_all_promo_codes()
        return {
            "success": True,
            "message": "Promo code detection completed",
            "results": results,
            "scraped_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Promo detection failed: {str(e)}"
        )


@router.post("/promos/{retailer_id}", response_model=dict)
def detect_retailer_promos(retailer_id: int, db: Session = Depends(get_db)):
    """
    Scan a single retailer's site for discount codes.
    """
    from app.models.models import Retailer

    retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()
    if not retailer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retailer with id {retailer_id} not found"
        )

    manager = ScrapeOrchestrator(db)
    try:
        results = manager.detect_promo_codes_for_retailer(retailer)
        return {
            "success": True,
            "message": f"Promo detection completed for {retailer.name}",
            "results": results,
            "scraped_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Promo detection failed: {str(e)}"
        )


@router.get("/test/the-last-hunt")
def test_the_last_hunt_scraper(
    brand: str = "Nike",
    model: str = "Vaporfly"
):
    """
    Test The Last Hunt scraper without database
    
    Quick test to verify scraper is working
    
    - **brand**: Shoe brand to search for
    - **model**: Shoe model to search for
    """
    from app.scrapers.the_last_hunt import TheLastHuntScraper
    
    scraper = TheLastHuntScraper()
    
    try:
        # Search for products
        products = scraper.search_products(brand, model)
        
        # Get details for first product if found
        product_details = []
        for product in products[:3]:  # Limit to first 3 to avoid long wait
            details = scraper.get_product_details(product['product_url'])
            if details:
                product_details.append(details)
        
        return {
            "success": True,
            "search_query": f"{brand} {model}",
            "products_found": len(products),
            "products": products,
            "detailed_results": product_details,
            "tested_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test failed: {str(e)}"
        )


@router.get("/test/altitude-sports")
def test_altitude_sports_scraper(
    brand: str = "Saucony",
    model: str = "Endorphin"
):
    """
    Test the Altitude Sports (Algolia) scraper without touching the database.
    """
    from app.scrapers.altitude_sports import AltitudeSportsScraper

    scraper = AltitudeSportsScraper()

    try:
        products = scraper.search_products(brand, model)
        product_details = []
        for product in products[:3]:
            details = scraper.get_product_details(product['product_url'])
            if details:
                product_details.append(details)

        return {
            "success": True,
            "search_query": f"{brand} {model}",
            "products_found": len(products),
            "products": products,
            "detailed_results": product_details,
            "tested_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test failed: {str(e)}"
        )


@router.get("/test/jd-sports")
def test_jd_sports_scraper(
    brand: str = "Adidas",
    model: str = "Adizero Boston 13"
):
    """
    Test the JD Sports (Shopify) scraper without touching the database.

    Defaults to the Adidas Adizero Boston 13 — the product the old scraper
    couldn't find.
    """
    from app.scrapers.jd_sports import JDSportsScraper

    scraper = JDSportsScraper()

    try:
        products = scraper.search_products(brand, model)

        product_details = []
        for product in products[:3]:
            details = scraper.get_product_details(product['product_url'])
            if details:
                product_details.append(details)

        return {
            "success": True,
            "search_query": f"{brand} {model}",
            "products_found": len(products),
            "products": products,
            "detailed_results": product_details,
            "tested_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test failed: {str(e)}"
        )
