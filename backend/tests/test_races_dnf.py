"""R10.3 — the `dnf` (did not finish) race status.

Rules under test: mark_dnf sets status, clears the result, keeps the linked run;
race day is allowed, a future race or a missing id is refused (ValueError /
LookupError → 400 / 404 over REST); a DNF'd race's run is never a Race PB (the
completed control is); a DNF is "done" for the next-race pick and is not the race
readiness is about; the MCP tool returns the write envelope both ways.
"""
import os

# Same token map as test_auth / test_http_smoke: the auth middleware is built
# lazily on the first request, so every module that drives the ASGI app must agree.
TEST_SECRET    = "test-anton-secret-0123456789abcdef"
TEST_OTHER     = "test-other-secret-0123456789abcd00"
TEST_CONNECTOR = "test-connector-secret-0123456789ab"
os.environ["ANTON_TOKENS"]          = f"desktop:{TEST_SECRET},spa:{TEST_OTHER}"
os.environ["ANTON_CONNECTOR_TOKEN"] = TEST_CONNECTOR

import asyncio  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from datetime import date, timedelta  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import mcp_server  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.models import Activity, PlannedRace  # noqa: E402
from app.services import races as races_svc  # noqa: E402
from app.services import strava_stats  # noqa: E402
from app.services.race_advisor import _readiness_race, race_block_context, race_readiness  # noqa: E402
from app.services.weekly_summary import weekly_summary  # noqa: E402

TODAY = date(2026, 10, 18)


def _run(db, day=None, km=14.0, *, tag=None):
    a = Activity(source="manual", activity_type="Run", run_date=day or TODAY - timedelta(days=1),
                 distance_km=km, elapsed_time_s=51 * 60, moving_time_s=51 * 60, activity_tag=tag)
    db.add(a)
    db.commit()
    return a


def _race(db, *, day=None, status="completed", activity=None, result_s=None, km=42.195,
          name="Beneva Marathon"):
    r = PlannedRace(name=name, race_date=day or TODAY - timedelta(days=1), distance_km=km,
                    status=status, result_time_s=result_s,
                    activity_id=activity.id if activity else None)
    db.add(r)
    db.commit()
    return r


# --- service ------------------------------------------------------------------------------

def test_mark_dnf_sets_status_clears_result_keeps_run(db):
    a = _run(db)
    r = _race(db, activity=a, result_s=3060)
    out = races_svc.mark_dnf(db, r.id, today=TODAY)
    assert out.status == "dnf"
    assert out.result_time_s is None
    assert out.activity_id == a.id


def test_mark_dnf_allows_race_day(db):
    r = _race(db, day=TODAY, status="planned")
    assert races_svc.mark_dnf(db, r.id, today=TODAY).status == "dnf"


def test_mark_dnf_rejects_a_future_race(db):
    r = _race(db, day=TODAY + timedelta(days=1), status="planned")
    with pytest.raises(ValueError):
        races_svc.mark_dnf(db, r.id, today=TODAY)
    db.refresh(r)
    assert r.status == "planned"


def test_mark_dnf_missing_race_is_lookup_error(db):
    with pytest.raises(LookupError):
        races_svc.mark_dnf(db, 9999, today=TODAY)


# --- REST ---------------------------------------------------------------------------------

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


def test_rest_dnf_ok(api):
    call, s = api
    r = _race(s, day=date.today() - timedelta(days=1), result_s=3060)
    resp = call("POST", f"/api/races/{r.id}/dnf")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "dnf" and body["result_time_s"] is None


def test_rest_dnf_missing_is_404(api):
    call, _ = api
    assert call("POST", "/api/races/9999/dnf").status_code == 404


def test_rest_dnf_future_is_400(api):
    call, s = api
    r = _race(s, day=date.today() + timedelta(days=30), status="planned")
    assert call("POST", f"/api/races/{r.id}/dnf").status_code == 400


# --- records ------------------------------------------------------------------------------

def _marathon_pbs(db):
    return [b for b in strava_stats.personal_bests(db).race_pbs if b.band == "full"]


def test_dnf_linked_race_tagged_run_is_not_a_race_pb(db):
    a = _run(db, km=42.2, tag="Race")
    _race(db, status="dnf", activity=a)
    assert _marathon_pbs(db) == []


def test_completed_control_is_a_race_pb(db):
    a = _run(db, km=42.2, tag="Race")
    _race(db, status="completed", activity=a, result_s=3060)
    pbs = _marathon_pbs(db)
    assert len(pbs) == 1 and pbs[0].activity_id == a.id


# --- next race / readiness ------------------------------------------------------------------

def test_weekly_summary_skips_a_dnf_race_today(db):
    _race(db, day=TODAY, status="dnf")
    _race(db, day=TODAY + timedelta(days=14), status="planned", name="Next One", km=10)
    assert weekly_summary(db, today=TODAY).next_race.name == "Next One"


def test_race_advisor_next_race_skips_a_dnf_race_today(db):
    _race(db, day=TODAY, status="dnf")
    assert race_block_context(db, today=TODAY).next_race is None
    _race(db, day=TODAY + timedelta(days=14), status="planned", name="Next One", km=10)
    assert race_block_context(db, today=TODAY).next_race.name == "Next One"


def test_readiness_skips_a_dnf_race(db):
    _race(db, day=TODAY + timedelta(days=3), status="dnf")
    assert _readiness_race(db, TODAY) is None
    assert race_readiness(db, as_of=TODAY).has_race is False
    nxt = _race(db, day=TODAY + timedelta(days=9), status="planned", name="Next One")
    assert _readiness_race(db, TODAY).id == nxt.id


# --- MCP ----------------------------------------------------------------------------------

def test_mcp_tool_envelopes(db, monkeypatch):
    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)

    r = _race(db, day=date.today() - timedelta(days=1), result_s=3060)
    ok = mcp_server.mark_race_dnf(r.id)
    assert ok["success"] is True
    assert ok["race"]["status"] == "dnf" and ok["race"]["result_time_s"] is None

    missing = mcp_server.mark_race_dnf(9999)
    assert missing["success"] is False and "9999" in missing["error"]

    future = _race(db, day=date.today() + timedelta(days=30), status="planned", name="Later")
    bad = mcp_server.mark_race_dnf(future.id)
    assert bad["success"] is False and "hasn't happened" in bad["error"]


def test_mark_dnf_defaults_to_the_toronto_date(db, monkeypatch):
    # UTC may already be "tomorrow"; the race dated Toronto-today must be allowed.
    monkeypatch.setattr(races_svc, "toronto_today", lambda: TODAY)
    r = _race(db, day=TODAY, status="planned")
    assert races_svc.mark_dnf(db, r.id).status == "dnf"
    later = _race(db, day=TODAY + timedelta(days=1), status="planned", name="Later")
    with pytest.raises(ValueError):
        races_svc.mark_dnf(db, later.id)
