"""R10.2 — the race-block retrospective over REST and MCP.

`GET /api/races/blocks` and the MCP tool `get_block_comparison` are thin adapters
over `race_advisor.block_comparison`. Rules under test: the REST route returns the
same blocks the service builds (16 weeks for a marathon), filters by race class,
and maps an unknown class to 400; the MCP tool returns a dict that validates
against the REST response schema, returns {"error": ...} for a bad class or a bad
as_of date, and honours as_of. The service's own rules are in test_block_comparison.py.
"""
import os

# Same token map as test_races_dnf / test_auth: the auth middleware is built
# lazily on the first request, so every module that drives the ASGI app must agree.
TEST_SECRET    = "test-anton-secret-0123456789abcdef"
TEST_OTHER     = "test-other-secret-0123456789abcd00"
TEST_CONNECTOR = "test-connector-secret-0123456789ab"
os.environ["ANTON_TOKENS"]          = f"desktop:{TEST_SECRET},spa:{TEST_OTHER}"
os.environ["ANTON_CONNECTOR_TOKEN"] = TEST_CONNECTOR

import asyncio  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from datetime import date  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import mcp_server  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.models import Activity, PlannedRace  # noqa: E402
from app.models.schemas import BlockComparisonResponse  # noqa: E402

AS_OF = "2026-10-20"
MARATHON_DAY = date(2026, 3, 1)      # completed; block runs 2025-11-10 .. 2026-02-28
HALF_DAY = date(2026, 6, 7)          # completed half, a different class


def _race(s, *, day, km, status="completed", name="Spring Marathon"):
    r = PlannedRace(name=name, race_date=day, distance_km=km, status=status)
    s.add(r)
    s.commit()
    return r


def _run(s, day, km):
    a = Activity(source="manual", activity_type="Run", run_date=day, distance_km=km,
                 elapsed_time_s=51 * 60, moving_time_s=51 * 60)
    s.add(a)
    s.commit()
    return a


@pytest.fixture()
def api():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    S = sessionmaker(bind=engine)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()

    from app.services.rate_limit import auth_failure_limiter
    auth_failure_limiter._buckets.clear()
    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db

    def call(method, path):
        async def _go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
                return await c.request(method, path, headers={"Authorization": f"Bearer {TEST_SECRET}"})
        return asyncio.run(_go())

    seed = S()
    yield call, seed
    seed.close()
    if prev is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = prev
    engine.dispose()


# --- REST ---------------------------------------------------------------------------------

def test_rest_blocks_marathon_has_sixteen_weeks(api):
    call, s = api
    _race(s, day=MARATHON_DAY, km=42.195)
    _run(s, date(2026, 2, 1), 20.0)
    resp = call("GET", f"/api/races/blocks?as_of={AS_OF}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["race_class"] == "marathon"
    assert len(body["blocks"]) == 1
    block = body["blocks"][0]
    assert len(block["weeks"]) == 16
    assert block["total_km"] == 20.0
    assert block["race"]["name"] == "Spring Marathon"


def test_rest_blocks_half_filters_to_its_class(api):
    call, s = api
    _race(s, day=MARATHON_DAY, km=42.195)
    _race(s, day=HALF_DAY, km=21.0975, name="Summer Half")
    resp = call("GET", f"/api/races/blocks?race_class=half&as_of={AS_OF}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["race_class"] == "half" and body["block_weeks"] == 12
    assert [b["race"]["name"] for b in body["blocks"]] == ["Summer Half"]
    assert len(body["blocks"][0]["weeks"]) == 12


def test_rest_blocks_unknown_class_is_400(api):
    call, _ = api
    resp = call("GET", f"/api/races/blocks?race_class=ultra&as_of={AS_OF}")
    assert resp.status_code == 400
    assert "ultra" in resp.json()["detail"]


def test_rest_blocks_bad_as_of_is_422(api):
    call, _ = api
    assert call("GET", "/api/races/blocks?as_of=not-a-date").status_code == 422


# --- MCP ----------------------------------------------------------------------------------

@pytest.fixture()
def mcp_session(db, monkeypatch):
    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)
    return db


def test_mcp_block_comparison_returns_blocks_matching_the_rest_schema(mcp_session):
    _race(mcp_session, day=MARATHON_DAY, km=42.195)
    _run(mcp_session, date(2026, 2, 1), 20.0)
    out = mcp_server.get_block_comparison(as_of=AS_OF)
    assert "error" not in out
    assert out["race_class"] == "marathon"
    assert len(out["blocks"]) == 1 and len(out["blocks"][0]["weeks"]) == 16
    # Same shape as the REST response, so the two surfaces can't drift.
    assert BlockComparisonResponse(**out).model_dump(mode="json") == out


def test_mcp_block_comparison_unknown_class_is_an_error_dict(mcp_session):
    out = mcp_server.get_block_comparison(race_class="ultra")
    assert set(out) == {"error"} and "ultra" in out["error"]


def test_mcp_block_comparison_bad_date_is_an_error_dict(mcp_session):
    out = mcp_server.get_block_comparison(as_of="20-10-2026")
    assert set(out) == {"error"}


def test_mcp_block_comparison_honours_as_of(mcp_session):
    _race(mcp_session, day=date(2026, 11, 1), km=42.195, status="planned", name="Autumn Marathon")

    early = mcp_server.get_block_comparison(as_of="2026-10-20")
    assert early["as_of"] == "2026-10-20"
    assert len(early["blocks"]) == 1
    assert early["blocks"][0]["in_progress"] is True
    assert early["blocks"][0]["block_end"] == "2026-10-20"   # cut at as_of

    # Once as_of passes the race date, the unfinished plan no longer counts.
    late = mcp_server.get_block_comparison(as_of="2026-11-05")
    assert late["blocks"] == []
