"""
Tests for R3.3 — shoe review pipeline.

Rules under test:
- rotation.store_shoe_review persists the text and returns the updated shoe
- A second call overwrites the previous draft (one review per shoe)
- store_shoe_review raises LookupError for a non-existent shoe
- review_draft is null by default
- The REST router update_shoe_review wires storage and 404 propagation
- OwnedShoeResponse schema exposes review_draft
"""
import pytest
from fastapi import HTTPException

from app.models.models import OwnedShoe
from app.models.schemas import ShoeReviewUpdate
from app.routers.owned_shoes import update_shoe_review, get_owned_shoe
from app.services import rotation


def _make_shoe(db, current_mileage: float = 100.0) -> OwnedShoe:
    shoe = OwnedShoe(
        brand="Adidas",
        model="Adizero Adios Pro 3",
        starting_mileage=current_mileage,
        current_mileage=current_mileage,
    )
    db.add(shoe)
    db.commit()
    db.refresh(shoe)
    return shoe


# ── service-layer tests ──────────────────────────────────────────────────────

def test_store_shoe_review_persists_text(db):
    """store_shoe_review writes the draft and returns the updated shoe."""
    shoe = _make_shoe(db)
    updated = rotation.store_shoe_review(db, shoe.id, "Great shoe for racing.")
    assert updated.review_draft == "Great shoe for racing."


def test_review_draft_null_by_default(db):
    """A freshly-created shoe has no review draft."""
    shoe = _make_shoe(db)
    db.refresh(shoe)
    assert shoe.review_draft is None


def test_store_shoe_review_overwrites_previous(db):
    """Calling store_shoe_review twice keeps only the latest text."""
    shoe = _make_shoe(db)
    rotation.store_shoe_review(db, shoe.id, "First draft.")
    rotation.store_shoe_review(db, shoe.id, "Revised review.")
    db.refresh(shoe)
    assert shoe.review_draft == "Revised review."


def test_store_shoe_review_missing_shoe_raises(db):
    """store_shoe_review raises LookupError for a non-existent shoe id."""
    with pytest.raises(LookupError):
        rotation.store_shoe_review(db, 9999, "Doesn't matter.")


def test_store_shoe_review_accepts_long_text(db):
    """review_draft can hold multi-paragraph text (Text column, no length cap)."""
    shoe = _make_shoe(db)
    long_review = "A" * 5000
    updated = rotation.store_shoe_review(db, shoe.id, long_review)
    assert updated.review_draft == long_review


# ── router-layer tests ───────────────────────────────────────────────────────

def test_update_shoe_review_stores_and_returns_shoe(db):
    """PATCH /owned-shoes/{id}/review stores the draft and returns the shoe."""
    shoe = _make_shoe(db)
    body = ShoeReviewUpdate(review_text="Carbon-plate racer, great for races.")
    result = update_shoe_review(shoe.id, body, db)
    # result is the shoe with computed fields attached
    db.refresh(shoe)
    assert shoe.review_draft == "Carbon-plate racer, great for races."


def test_update_shoe_review_not_found_raises_404(db):
    """PATCH /owned-shoes/9999/review raises a 404 HTTPException."""
    body = ShoeReviewUpdate(review_text="Anything.")
    with pytest.raises(HTTPException) as exc_info:
        update_shoe_review(9999, body, db)
    assert exc_info.value.status_code == 404


def test_get_owned_shoe_exposes_review_draft(db):
    """GET /owned-shoes/{id} response includes review_draft field."""
    shoe = _make_shoe(db)
    rotation.store_shoe_review(db, shoe.id, "Review text here.")
    result = get_owned_shoe(shoe.id, db)
    # result is the ORM object with computed fields; review_draft should be set
    assert result.review_draft == "Review text here."


def test_get_owned_shoe_review_draft_none_when_unset(db):
    """GET /owned-shoes/{id} exposes null review_draft when no review written."""
    shoe = _make_shoe(db)
    result = get_owned_shoe(shoe.id, db)
    assert result.review_draft is None
