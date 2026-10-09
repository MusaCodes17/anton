"""
HTTP layer for chat confirmation cards (R7.2): the three /api/chat/proposals
routes map service outcomes to status codes and never run a call twice.
The executor is stubbed — test_chat_proposals covers the real MCP path.

Env values must match test_auth / test_http_smoke exactly (the middleware is
built lazily from whichever module's env is active first).
"""
import os

TEST_SECRET    = "test-anton-secret-0123456789abcdef"
TEST_OTHER     = "test-other-secret-0123456789abcd00"
TEST_CONNECTOR = "test-connector-secret-0123456789ab"
os.environ["ANTON_TOKENS"]          = f"desktop:{TEST_SECRET},spa:{TEST_OTHER}"
os.environ["ANTON_CONNECTOR_TOKEN"] = TEST_CONNECTOR

import asyncio  # noqa: E402
import json  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import chat as chat_router  # noqa: E402
from app.services import chat_proposals as cp  # noqa: E402

AUTH = {"Authorization": f"Bearer {TEST_SECRET}"}


@pytest.fixture(autouse=True)
def _clean_registry():
    cp._proposals.clear()
    yield
    cp._proposals.clear()


@pytest.fixture()
def calls(monkeypatch):
    seen = []

    async def fake_executor(name, args):
        seen.append((name, args))
        return json.dumps({"success": True, "new_mileage": 512.4}), True

    monkeypatch.setattr(chat_router, "call_tool_once", fake_executor)
    return seen


def _request(method, path, **kw):
    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, headers=AUTH, **kw)
    return asyncio.run(go())


def test_confirm_twice_runs_once(db, calls):
    p = cp.create(db, "retire_shoe", {"owned_shoe_id": 1})
    first = _request("POST", f"/api/chat/proposals/{p.id}/confirm")
    second = _request("POST", f"/api/chat/proposals/{p.id}/confirm")
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "done"
    assert first.json()["result"]["success"] is True
    assert "tapped Confirm" in first.json()["followup_message"]
    assert calls == [("retire_shoe", {"owned_shoe_id": 1})]


def test_cancel_then_confirm_is_409_and_runs_nothing(db, calls):
    p = cp.create(db, "retire_shoe", {"owned_shoe_id": 1})
    r = _request("POST", f"/api/chat/proposals/{p.id}/cancel", json={})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert _request("POST", f"/api/chat/proposals/{p.id}/confirm").status_code == 409
    assert calls == []


def test_cancel_after_confirm_is_409(db, calls):
    p = cp.create(db, "retire_shoe", {"owned_shoe_id": 1})
    _request("POST", f"/api/chat/proposals/{p.id}/confirm")
    assert _request("POST", f"/api/chat/proposals/{p.id}/cancel", json={}).status_code == 409


def test_unknown_proposal_is_404(calls):
    assert _request("GET", "/api/chat/proposals/nope").status_code == 404
    assert _request("POST", "/api/chat/proposals/nope/confirm").status_code == 404
    assert calls == []


def test_routes_require_auth(db):
    p = cp.create(db, "retire_shoe", {"owned_shoe_id": 1})

    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(f"/api/chat/proposals/{p.id}/confirm")

    # 401, or 429 once other modules have drained the shared auth-failure
    # limiter — either way the request is rejected and nothing runs.
    assert asyncio.run(go()).status_code in (401, 429)
    assert cp.get(p.id).status == "pending"
