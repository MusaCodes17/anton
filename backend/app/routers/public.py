"""
Public (logged-out) data surface — R9.3. Anton's first deliberately public data
endpoint; its exact path is the only /api/public entry in `PUBLIC_PATHS`.

Takes NO query params on purpose: no filter means no new input surface to
validate, and every client gets the same cacheable body. It returns its own
`PublicDealsResponse` schema rather than `DealResponse` because the owner
payload carries personal fields (`notes`, `target_price`, `size_fit`) that must
never go public; the public schema is built field by field in the service.
Rate-limited per client IP; does no scrape or sync work.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import _client_ip
from app.models.schemas import PublicDealsResponse
from app.services import deals as deals_svc
from app.services.rate_limit import public_limiter

# Module-level reference so tests can monkeypatch it (mirrors routers/session.py).
_public_limiter = public_limiter

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/deals", response_model=PublicDealsResponse)
def public_deals(request: Request, response: Response, db: Session = Depends(get_db)):
    """Active deals, field-allowlisted, biggest discount first (R9.3)."""
    result = _public_limiter.take(_client_ip(request.scope))
    if not result.allowed:
        return Response(
            status_code=429,
            headers={"Retry-After": str(max(1, int(result.retry_after_s)))},
        )
    response.headers["Cache-Control"] = "public, max-age=300"
    return deals_svc.list_public_deals(db)
