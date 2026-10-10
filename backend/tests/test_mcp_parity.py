"""MCP tools render owned shoes, runs, notes and watchlist entries through the same
Pydantic schemas REST uses (tech-debt §7 P1), so the two surfaces can't drift."""
from contextlib import contextmanager
from datetime import date

import pytest

from app import mcp_server
from app.models.models import OwnedShoe, Retailer, Shoe, ShoeNote
from app.models.schemas import OwnedShoeResponse, ShoeNoteResponse
from app.routers import owned_shoes as owned_shoes_router
from app.services import rotation


@pytest.fixture()
def mcp_db(db, monkeypatch):
    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)
    return db


def _shoe_with_run_and_note(db):
    shoe = OwnedShoe(brand="Nike", model="Pegasus", shoe_type="daily", starting_mileage=10.0,
                     current_mileage=10.0, purchase_price=150.0)
    db.add(shoe)
    db.commit()
    db.refresh(shoe)
    rotation.log_run(db, shoe.id, distance_km=12.0, run_date=date(2026, 7, 1),
                     avg_pace="5:00/km", avg_hr=150, notes="easy")
    db.add(ShoeNote(owned_shoe_id=shoe.id, body="Feels great", mileage_at_note=22.0, triggered_by="manual"))
    db.commit()
    return shoe


def test_owned_shoes_tool_matches_rest(mcp_db):
    shoe = _shoe_with_run_and_note(mcp_db)
    rest = [OwnedShoeResponse.model_validate(s).model_dump(mode="json")
            for s in owned_shoes_router.get_owned_shoes(db=mcp_db)]
    mcp = mcp_server.get_owned_shoes()
    assert [m for m in mcp if m["id"] == shoe.id] == [r for r in rest if r["id"] == shoe.id]
    assert mcp[0]["total_runs"] == 1 and mcp[0]["cost_per_km"] is not None


def test_shoe_runs_tool_keeps_legacy_keys(mcp_db):
    shoe = _shoe_with_run_and_note(mcp_db)
    runs = mcp_server.get_shoe_runs(shoe.id)["runs"]
    assert len(runs) == 1
    assert {"id", "owned_shoe_id", "distance_km", "run_date", "source", "avg_pace", "avg_hr", "notes"} <= set(runs[0])
    assert runs[0]["run_date"] == "2026-07-01" and runs[0]["distance_km"] == 12.0


def test_shoe_notes_tool_matches_rest(mcp_db):
    shoe = _shoe_with_run_and_note(mcp_db)
    rest = [ShoeNoteResponse.model_validate(n).model_dump(mode="json")
            for n in owned_shoes_router.get_shoe_notes(shoe.id, db=mcp_db)]
    assert mcp_server.get_shoe_notes(shoe.id) == rest and len(rest) == 1


def test_watchlist_tool_keeps_legacy_keys(mcp_db):
    mcp_db.add(Shoe(brand="Adidas", model="Adios Pro 3", msrp=300.0, is_active=True))
    mcp_db.add(Retailer(name="R", base_url="https://r.example"))
    mcp_db.commit()
    entries = mcp_server.get_watchlist()
    assert len(entries) == 1
    assert {"shoe_id", "brand", "model", "shoe_type", "msrp", "target_price", "image_url", "on_sale",
            "best_deal", "best_ever_price", "best_ever_at", "last_seen"} <= set(entries[0])
