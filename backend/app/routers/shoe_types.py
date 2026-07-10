"""
Shoe-type vocabulary API (R2.4).

Serves the backend-owned `shoe_type` controlled vocabulary so the frontend keeps
no independent copy — the same pattern as `GET /api/activities/tags` for activity
tags. A dedicated router (not folded into `shoes` or `owned-shoes`) because the
vocabulary is the cross-domain join key shared by *both* domains (a `Shoe` and an
`OwnedShoe`), owned by neither. See `app/utils/shoe_types.py`.
"""
from typing import List

from fastapi import APIRouter

from app.utils.shoe_types import SHOE_TYPES

router = APIRouter(prefix="/shoe-types", tags=["shoe-types"])


@router.get("", response_model=List[str])
@router.get("/", response_model=List[str])
def get_shoe_types():
    """The ordered `shoe_type` controlled vocabulary (canonical snake_case
    values). The frontend fetches this instead of hard-coding the list; display
    labels are derived client-side by title-casing (presentation only)."""
    return list(SHOE_TYPES)
