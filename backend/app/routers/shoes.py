"""
API routes for managing shoes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import (
    Shoe, ShoeCreate, ShoeUpdate, ShoeResponse, ShoeTestRequest
)
from app.models.models import Deal, PriceRecord
from app.scrapers.orchestrator import ScrapeOrchestrator

router = APIRouter(prefix="/shoes", tags=["shoes"])


@router.post("/test", response_model=dict)
def test_shoe_scrapability(payload: ShoeTestRequest, db: Session = Depends(get_db)):
    """
    Dry-run a brand+model search across active retailers to check whether a
    shoe (new or already saved) is actually findable, before/without saving
    it. Never writes to the database.
    """
    manager = ScrapeOrchestrator(db)
    try:
        return manager.test_shoe_scrapability(payload.brand.strip(), payload.model.strip())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scrapability test failed: {str(e)}"
        )


@router.get("/", response_model=List[ShoeResponse])
def get_shoes(
    skip: int = 0,
    limit: int = 100,
    brand: str = None,
    is_active: bool = None,
    db: Session = Depends(get_db)
):
    """
    Get all shoes with optional filtering
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **brand**: Filter by brand (optional)
    - **is_active**: Filter by active status (optional)
    """
    query = db.query(Shoe)
    
    if brand:
        query = query.filter(Shoe.brand.ilike(f"%{brand}%"))
    
    if is_active is not None:
        query = query.filter(Shoe.is_active == is_active)
    
    shoes = query.offset(skip).limit(limit).all()
    return shoes


@router.get("/summary", response_model=List[dict])
def get_shoes_summary(db: Session = Depends(get_db)):
    """
    Bulk per-shoe summary for the Shoes list page: a default price, image,
    and retailer count derived from the LATEST price record per retailer —
    regardless of whether that price is currently a "deal". Without this,
    shoes with no active deal would show a blank price/image/retailer count
    even though we've successfully scraped them. One query for all shoes
    (not per-shoe) to avoid an N+1 fetch from the list page.
    """
    rn = (
        func.row_number()
        .over(
            partition_by=[PriceRecord.shoe_id, PriceRecord.retailer_id],
            order_by=PriceRecord.scraped_at.desc(),
        )
        .label("rn")
    )
    ranked = db.query(
        PriceRecord.shoe_id.label("shoe_id"),
        PriceRecord.retailer_id.label("retailer_id"),
        PriceRecord.price.label("price"),
        PriceRecord.image_url.label("image_url"),
        rn,
    ).subquery()
    latest = db.query(ranked).filter(ranked.c.rn == 1).subquery()

    aggregates = (
        db.query(
            latest.c.shoe_id,
            func.min(latest.c.price).label("default_price"),
            func.count(latest.c.retailer_id).label("retailers_scraped"),
        )
        .group_by(latest.c.shoe_id)
        .all()
    )

    # Any real product image is fine ("any colorway") — use the cheapest
    # retailer's image so it lines up with default_price above.
    image_by_shoe = {}
    for shoe_id, price, image_url in (
        db.query(latest.c.shoe_id, latest.c.price, latest.c.image_url)
        .filter(latest.c.image_url.isnot(None))
        .order_by(latest.c.shoe_id, latest.c.price.asc())
        .all()
    ):
        image_by_shoe.setdefault(shoe_id, image_url)

    return [
        {
            "shoe_id": shoe_id,
            "default_price": default_price,
            "retailers_scraped": retailers_scraped,
            "image_url": image_by_shoe.get(shoe_id),
        }
        for shoe_id, default_price, retailers_scraped in aggregates
    ]


@router.get("/{shoe_id}", response_model=ShoeResponse)
def get_shoe(shoe_id: int, db: Session = Depends(get_db)):
    """
    Get a specific shoe by ID
    """
    shoe = db.query(Shoe).filter(Shoe.id == shoe_id).first()
    
    if not shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shoe with id {shoe_id} not found"
        )
    
    return shoe


@router.post("/", response_model=ShoeResponse, status_code=status.HTTP_201_CREATED)
def create_shoe(shoe: ShoeCreate, db: Session = Depends(get_db)):
    """
    Create a new shoe to track
    """
    db_shoe = Shoe(**shoe.model_dump())
    db.add(db_shoe)
    db.commit()
    db.refresh(db_shoe)
    return db_shoe


@router.put("/{shoe_id}", response_model=ShoeResponse)
def update_shoe(shoe_id: int, shoe_update: ShoeUpdate, db: Session = Depends(get_db)):
    """
    Update an existing shoe
    """
    db_shoe = db.query(Shoe).filter(Shoe.id == shoe_id).first()
    
    if not db_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shoe with id {shoe_id} not found"
        )
    
    # Update only provided fields
    update_data = shoe_update.model_dump(exclude_unset=True)
    identity_changed = (
        ("brand" in update_data and update_data["brand"] != db_shoe.brand)
        or ("model" in update_data and update_data["model"] != db_shoe.model)
    )
    for field, value in update_data.items():
        setattr(db_shoe, field, value)

    if identity_changed:
        # Existing deals/price_records were scraped against the OLD brand/model —
        # they no longer describe the renamed shoe, so they'd otherwise keep
        # displaying a stale, mismatched product under the new name until the
        # next scrape happens to overwrite them.
        db.query(Deal).filter(Deal.shoe_id == db_shoe.id, Deal.is_active == True).update(
            {Deal.is_active: False}
        )

    db.commit()
    db.refresh(db_shoe)
    return db_shoe


@router.delete("/{shoe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shoe(shoe_id: int, db: Session = Depends(get_db)):
    """
    Delete a shoe
    """
    db_shoe = db.query(Shoe).filter(Shoe.id == shoe_id).first()
    
    if not db_shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shoe with id {shoe_id} not found"
        )
    
    db.delete(db_shoe)
    db.commit()
    return None


@router.get("/{shoe_id}/prices", response_model=List[dict])
def get_shoe_price_history(
    shoe_id: int,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Get price history for a specific shoe
    """
    shoe = db.query(Shoe).filter(Shoe.id == shoe_id).first()
    
    if not shoe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shoe with id {shoe_id} not found"
        )
    
    # Get price records ordered by date
    price_records = []
    for record in shoe.price_records[:limit]:
        price_records.append({
            "id": record.id,
            "retailer_id": record.retailer_id,
            "retailer_name": record.retailer.name,
            "price": record.price,
            "original_price": record.original_price,
            "in_stock": record.in_stock,
            "product_url": record.product_url,
            "image_url": record.image_url,
            "colorway": record.colorway,
            "scraped_at": record.scraped_at
        })
    
    return price_records
