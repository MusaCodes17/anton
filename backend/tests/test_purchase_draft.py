"""R5.3 "Bought it" — the purchase draft built from a deal.

Rules pinned here: the draft maps deal/shoe/retailer fields as specified; the
watchlist shoe_type passes through only when it is in the owned-shoe vocabulary;
an expired deal still drafts (deal_active=False); a missing deal is a 404 over
REST and an error dict over MCP; REST and MCP return the same payload; and
drafting writes nothing (B1 — wanting is not owning).
"""
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi import HTTPException

from app import mcp_server
from app.models.models import Deal, OwnedShoe, Retailer, Shoe
from app.routers import deals as deals_router
from app.services import purchase_draft as purchase_draft_svc
from app.services.purchase_draft import purchase_draft_from_deal

PINNED_TODAY = date(2026, 10, 10)


@pytest.fixture()
def pinned(db, monkeypatch):
    """Pin the Toronto date and route MCP tools at the test session."""
    monkeypatch.setattr(purchase_draft_svc, "toronto_today", lambda: PINNED_TODAY)

    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)
    return db


def _deal(db, *, shoe_type="long_distance_racer", is_active=True, colorway="Black / White"):
    retailer = Retailer(name="The Last Hunt", base_url="https://thelasthunt.example")
    shoe = Shoe(brand="Adidas", model="Adizero Adios Pro 4", msrp=300.0, shoe_type=shoe_type)
    db.add_all([retailer, shoe])
    db.flush()
    deal = Deal(
        shoe_id=shoe.id, retailer_id=retailer.id, current_price=219.99,
        savings_amount=80.01, savings_percent=26.7,
        product_url="https://thelasthunt.example/adios-pro-4",
        image_url="https://cdn.example/adios.jpg", colorway=colorway,
        is_active=is_active,
    )
    db.add(deal)
    db.commit()
    return deal


# --- 1. Field mapping ----------------------------------------------------------------------

def test_draft_maps_deal_shoe_and_retailer_fields(db):
    deal = _deal(db)
    draft = purchase_draft_from_deal(db, deal.id, today=PINNED_TODAY)

    assert draft.brand == "Adidas"
    assert draft.model == "Adizero Adios Pro 4"
    assert draft.purchase_price == 219.99          # the deal's current_price
    assert draft.purchase_date == PINNED_TODAY     # pinned via `today`
    assert draft.purchase_retailer == "The Last Hunt"
    assert draft.purchase_url == "https://thelasthunt.example/adios-pro-4"
    assert draft.image_url == "https://cdn.example/adios.jpg"
    assert draft.colorway == "Black / White"
    assert draft.deal_id == deal.id
    assert draft.deal_active is True


def test_purchase_date_defaults_to_toronto_today(db, pinned):
    deal = _deal(db)
    assert purchase_draft_from_deal(db, deal.id).purchase_date == PINNED_TODAY


# --- 2. Vocabulary guard on shoe_type --------------------------------------------------------

def test_valid_watchlist_shoe_type_passes_through(db):
    deal = _deal(db, shoe_type="tempo")
    assert purchase_draft_from_deal(db, deal.id, today=PINNED_TODAY).shoe_type == "tempo"


def test_off_vocabulary_shoe_type_becomes_none(db):
    deal = _deal(db, shoe_type="Super racer 2000")
    assert purchase_draft_from_deal(db, deal.id, today=PINNED_TODAY).shoe_type is None


def test_missing_shoe_type_becomes_none(db):
    deal = _deal(db, shoe_type=None)
    assert purchase_draft_from_deal(db, deal.id, today=PINNED_TODAY).shoe_type is None


# --- 3. Expired deals still draft ----------------------------------------------------------

def test_inactive_deal_still_drafts_with_deal_active_false(db):
    deal = _deal(db, is_active=False)
    draft = purchase_draft_from_deal(db, deal.id, today=PINNED_TODAY)
    assert draft.deal_active is False
    assert draft.purchase_price == 219.99


# --- 4. Missing deal ------------------------------------------------------------------------

def test_missing_deal_raises_lookup_error(db):
    with pytest.raises(LookupError):
        purchase_draft_from_deal(db, 999_999, today=PINNED_TODAY)


def test_rest_missing_deal_is_404(db, pinned):
    with pytest.raises(HTTPException) as exc:
        deals_router.get_purchase_draft(999_999, db=db)
    assert exc.value.status_code == 404


def test_mcp_missing_deal_returns_error_dict(pinned):
    result = mcp_server.draft_purchase_from_deal(999_999)
    assert set(result) == {"error"}
    assert "999999" in result["error"]


# --- 5. REST == MCP parity -------------------------------------------------------------------

def test_endpoint_and_mcp_tool_agree(db, pinned):
    deal = _deal(db, shoe_type="daily_trainer")

    rest = deals_router.get_purchase_draft(deal.id, db=db).model_dump(mode="json")
    mcp = mcp_server.draft_purchase_from_deal(deal.id)

    assert rest == mcp
    assert rest["purchase_date"] == "2026-10-10"   # ISO string in JSON mode
    assert rest["shoe_type"] == "daily_trainer"


# --- 6. Nothing is written -------------------------------------------------------------------

def test_drafting_writes_nothing(db, pinned):
    deal = _deal(db)
    counts_before = (db.query(OwnedShoe).count(), db.query(Shoe).count(), db.query(Deal).count())

    purchase_draft_from_deal(db, deal.id)
    deals_router.get_purchase_draft(deal.id, db=db)
    mcp_server.draft_purchase_from_deal(deal.id)

    counts_after = (db.query(OwnedShoe).count(), db.query(Shoe).count(), db.query(Deal).count())
    assert counts_after == counts_before
    assert counts_before[0] == 0
