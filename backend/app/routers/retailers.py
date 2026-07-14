"""
API routes for managing retailers
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import (
    Retailer, RetailerCreate, RetailerUpdate, RetailerResponse,
    PromoCode, PromoCodeCreate, PromoCodeResponse
)
from app.scrapers.platform_detection import determine_platform, PlatformDetectionError
from app.services import onboarding as onboarding_svc

router = APIRouter(prefix="/retailers", tags=["retailers"])


@router.get("/", response_model=List[RetailerResponse])
def get_retailers(
    skip: int = 0,
    limit: int = 100,
    is_active: bool = None,
    scraping_enabled: bool = None,
    db: Session = Depends(get_db)
):
    """
    Get all retailers with optional filtering
    
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **is_active**: Filter by active status (optional)
    - **scraping_enabled**: Filter by scraping status (optional)
    """
    query = db.query(Retailer)
    
    if is_active is not None:
        query = query.filter(Retailer.is_active == is_active)
    
    if scraping_enabled is not None:
        query = query.filter(Retailer.scraping_enabled == scraping_enabled)
    
    retailers = query.offset(skip).limit(limit).all()
    return retailers


@router.get("/{retailer_id}", response_model=RetailerResponse)
def get_retailer(retailer_id: int, db: Session = Depends(get_db)):
    """
    Get a specific retailer by ID
    """
    retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()
    
    if not retailer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retailer with id {retailer_id} not found"
        )
    
    return retailer


@router.post("/", response_model=RetailerResponse, status_code=status.HTTP_201_CREATED)
def create_retailer(retailer: RetailerCreate, db: Session = Depends(get_db)):
    """
    Create a new retailer
    """
    # Check if retailer with same name already exists
    existing = db.query(Retailer).filter(Retailer.name == retailer.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Retailer with name '{retailer.name}' already exists"
        )
    
    data = retailer.model_dump()
    requested_platform = data.pop("platform", None)

    try:
        platform, force_scraping_enabled = determine_platform(
            base_url=data["base_url"],
            requested_platform=requested_platform,
            scraper_config=data.get("scraper_config"),
        )
    except PlatformDetectionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    data["platform"] = platform
    data["scraping_enabled"] = force_scraping_enabled

    db_retailer = Retailer(**data)
    db.add(db_retailer)
    db.commit()
    db.refresh(db_retailer)
    return db_retailer


@router.put("/{retailer_id}", response_model=RetailerResponse)
def update_retailer(
    retailer_id: int,
    retailer_update: RetailerUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing retailer
    """
    db_retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()
    
    if not db_retailer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retailer with id {retailer_id} not found"
        )
    
    # Update only provided fields
    update_data = retailer_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_retailer, field, value)
    
    db.commit()
    db.refresh(db_retailer)
    return db_retailer


@router.delete("/{retailer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_retailer(retailer_id: int, db: Session = Depends(get_db)):
    """
    Delete a retailer
    """
    db_retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()

    if not db_retailer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retailer with id {retailer_id} not found"
        )

    db.delete(db_retailer)
    db.commit()
    return None


# ============== ONBOARDING (R4.6) ==============


class RetailerProbeRequest(BaseModel):
    sample_brand: Optional[str] = None
    sample_model: Optional[str] = None


class RetailerOnboardRequest(BaseModel):
    platform: str
    scraper_config: Optional[dict] = None


class RetailerUnscrapableRequest(BaseModel):
    reason: str


@router.get("/onboarding/queue", response_model=List[dict])
def get_onboarding_queue(db: Session = Depends(get_db)):
    """
    Active retailers with no working scraper (and not marked unscrapable) —
    the onboarding queue. Mirrors scrape_health's `needs_onboarding`.
    """
    return onboarding_svc.retailers_needing_onboarding(db)


@router.post("/{retailer_id}/probe", response_model=dict)
def probe_retailer(
    retailer_id: int,
    payload: RetailerProbeRequest = RetailerProbeRequest(),
    db: Session = Depends(get_db),
):
    """
    Read-only scrapability probe: sniff the platform and dry-run a product
    search. Never writes. Returns the findings for the onboarding decision.
    """
    try:
        return onboarding_svc.probe_retailer(
            db, retailer_id,
            sample_brand=payload.sample_brand,
            sample_model=payload.sample_model,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{retailer_id}/onboard", response_model=RetailerResponse)
def onboard_retailer(
    retailer_id: int,
    payload: RetailerOnboardRequest,
    db: Session = Depends(get_db),
):
    """
    Wire a detected platform onto a retailer and enable scraping (the write
    step of onboarding). platform must be "shopify" or "algolia".
    """
    try:
        return onboarding_svc.apply_onboarding(
            db, retailer_id,
            platform=payload.platform,
            scraper_config=payload.scraper_config,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{retailer_id}/mark-unscrapable", response_model=RetailerResponse)
def mark_retailer_unscrapable(
    retailer_id: int,
    payload: RetailerUnscrapableRequest,
    db: Session = Depends(get_db),
):
    """
    Record the honest "no scraper worth building" verdict on a retailer, so it
    leaves the onboarding queue and the watchdog stops nagging.
    """
    try:
        return onboarding_svc.mark_unscrapable(db, retailer_id, reason=payload.reason)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============== PROMO CODES ==============

@router.get("/{retailer_id}/promos", response_model=List[PromoCodeResponse])
def get_retailer_promos(
    retailer_id: int,
    is_active: bool = True,
    db: Session = Depends(get_db)
):
    """
    List discount codes for a retailer (active only by default).
    """
    retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()
    if not retailer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retailer with id {retailer_id} not found"
        )

    query = db.query(PromoCode).filter(PromoCode.retailer_id == retailer_id)
    if is_active is not None:
        query = query.filter(PromoCode.is_active == is_active)

    return query.order_by(PromoCode.detected_at.desc()).all()


@router.post(
    "/{retailer_id}/promos",
    response_model=PromoCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_retailer_promo(
    retailer_id: int,
    promo: PromoCodeCreate,
    db: Session = Depends(get_db)
):
    """
    Manually add a discount code for a retailer. If the code already exists it
    is reactivated and updated.
    """
    retailer = db.query(Retailer).filter(Retailer.id == retailer_id).first()
    if not retailer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retailer with id {retailer_id} not found"
        )

    existing = db.query(PromoCode).filter(
        PromoCode.retailer_id == retailer_id,
        PromoCode.code == promo.code,
    ).first()

    if existing:
        existing.description = promo.description
        existing.discount_percent = promo.discount_percent
        existing.discount_amount = promo.discount_amount
        existing.source = "manual"
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    db_promo = PromoCode(
        retailer_id=retailer_id,
        source="manual",
        is_active=True,
        **promo.model_dump(),
    )
    db.add(db_promo)
    db.commit()
    db.refresh(db_promo)
    return db_promo


@router.delete("/promos/{promo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promo(promo_id: int, db: Session = Depends(get_db)):
    """
    Delete a discount code.
    """
    promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
    if not promo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Promo code with id {promo_id} not found"
        )
    db.delete(promo)
    db.commit()
    return None
