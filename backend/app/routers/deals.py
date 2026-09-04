"""
Deals API — thin adapter over services/deals.py.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DealResponse
from app.services import deals as deals_svc

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("/", response_model=List[DealResponse])
def get_deals(
    skip: int = 0,
    limit: int = 500,
    is_active: bool = True,
    min_savings_percent: Optional[float] = Query(None, ge=0, le=100),
    brand: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return deals_svc.list_deals(
        db,
        is_active=is_active,
        min_savings_percent=min_savings_percent,
        brand=brand,
        skip=skip,
        limit=limit,
    )


@router.get("/{deal_id}", response_model=DealResponse)
def get_deal(deal_id: int, db: Session = Depends(get_db)):
    deal = deals_svc.get_deal(db, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Deal {deal_id} not found")
    return deal


@router.put("/{deal_id}/deactivate", response_model=DealResponse)
def deactivate_deal(deal_id: int, db: Session = Depends(get_db)):
    try:
        return deals_svc.deactivate_deal(db, deal_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/shoe/{shoe_id}", response_model=List[DealResponse])
def get_deals_for_shoe(
    shoe_id: int,
    is_active: bool = True,
    db: Session = Depends(get_db),
):
    return deals_svc.get_deals_for_shoe(db, shoe_id, is_active=is_active)


@router.get("/retailer/{retailer_id}", response_model=List[DealResponse])
def get_deals_for_retailer(
    retailer_id: int,
    is_active: bool = True,
    db: Session = Depends(get_db),
):
    return deals_svc.get_deals_for_retailer(db, retailer_id, is_active=is_active)
