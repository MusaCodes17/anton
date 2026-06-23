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

from mcp.server.fastmcp import FastMCP
from sqlalchemy import desc, func

from app.database import SessionLocal
from app.models.models import Deal, PriceRecord, Retailer, Shoe
from app.scrapers.scraper_manager import ScraperManager

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
        limit: Max number of deals to return (default 20, capped at 100).
    """
    limit = max(1, min(limit, 100))

    with get_session() as db:
        query = db.query(Deal).filter(Deal.is_active == True)
        if min_savings_percent is not None:
            query = query.filter(Deal.savings_percent >= min_savings_percent)
        if brand:
            query = query.join(Deal.shoe).filter(Shoe.brand.ilike(f"%{brand}%"))
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
    with get_session() as db:
        shoe = Shoe(brand=brand.strip(), model=model.strip(), target_price=target_price, msrp=msrp)
        db.add(shoe)
        db.commit()
        db.refresh(shoe)
        return {
            "id": shoe.id,
            "brand": shoe.brand,
            "model": shoe.model,
            "target_price": shoe.target_price,
            "msrp": shoe.msrp,
            "is_active": shoe.is_active,
        }


@mcp.tool()
def trigger_scrape(shoe_id: Optional[int] = None) -> dict:
    """
    Scrape retailers for current prices and detect new deals.

    Scrapes one shoe if shoe_id is given, otherwise every actively-tracked
    shoe across every enabled retailer — which can take a while (it's a
    real, synchronous scrape of live retailer sites, not a queued job).
    Calls the same ScraperManager the REST API's /api/scrape endpoints use.

    Args:
        shoe_id: ID of a specific shoe to scrape (from get_shoes). Omit to
            scrape every active shoe.
    """
    with get_session() as db:
        manager = ScraperManager(db)
        if shoe_id is not None:
            shoe = db.query(Shoe).filter(Shoe.id == shoe_id).first()
            if not shoe:
                return {"success": False, "error": f"Shoe with id {shoe_id} not found"}
            results = manager.scrape_shoe(shoe_id)
        else:
            results = manager.scrape_all_shoes()
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
