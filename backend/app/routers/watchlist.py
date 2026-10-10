"""
Watchlist API — the data behind the redesigned Deals page (Phase 2).

Answers "what am I watching and what's actionable" for every tracked shoe in
one round trip, not just the on-sale subset: current best active deal (if
any), best-ever price + when, and the last-seen price at each retailer.

Deliberately one endpoint so the page (and the future mobile client) loads
the whole watchlist in a single request. Thin adapter over
`services.watchlist.build_watchlist` (R2.3) — the reduction lives in the
service; this file only shapes the HTTP response.
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.schemas import WatchlistItem
from app.services import watchlist as watchlist_svc

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=List[WatchlistItem])
@router.get("/", response_model=List[WatchlistItem])
def get_watchlist(db: Session = Depends(get_db)):
    """
    Every actively-tracked shoe with its best deal, best-ever price, and
    last-seen price per retailer, already ordered on-sale-first (see
    `services.watchlist.build_watchlist`). Pydantic reads the service dataclasses
    field-for-field via `from_attributes`.
    """
    return watchlist_svc.build_watchlist(db)
