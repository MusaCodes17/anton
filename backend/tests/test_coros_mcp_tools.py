"""COROS direct sync §7 — the Anton MCP tools share the app's queue.

Rules under test: Claude and the app see one inbox; confirming through either
clears it for the other; no path can log the same label_id twice (INV-5); the
status tool reports poller/connection truth; the prompt no longer routes
through the COROS connector for logging.
"""
import asyncio
import os
from contextlib import contextmanager
from datetime import date

os.environ.setdefault("ANTON_TOKENS", "desktop:test-mcp-token-0123456789abcdef")

import pytest
from cryptography.fernet import Fernet

from app import mcp_server
from app.models.models import (
    Activity, CorosConnection, CorosSyncState, OwnedShoe, PendingCorosRun,
)
from app.services import coros as coros_svc
from app.services import coros_inbox as inbox


@pytest.fixture(autouse=True)
def _session(db, monkeypatch):
    @contextmanager
    def fake_session():
        yield db          # share the test session; the fixture owns closing it
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)
    monkeypatch.setenv("COROS_TOKEN_KEY", Fernet.generate_key().decode())


def shoe(db, mileage=100.0):
    s = OwnedShoe(brand="Nike", model="Pegasus", shoe_type="daily_trainer", starting_mileage=mileage,
                  current_mileage=mileage, status="active")
    db.add(s)
    db.commit()
    return s


def pending(db, label="480000000000000001", **kw):
    vals = dict(label_id=label, sport_type=100, run_date=date(2026, 10, 6), distance_km=12.53,
                moving_time_s=3159, elapsed_time_s=3163, avg_pace_s_per_km=252, avg_hr=171,
                calories=710.0, elevation_gain_m=60.0, avg_cadence=186.0, training_load=113.0,
                training_focus="Base", start_timestamp=1, end_timestamp=2, status="pending")
    vals.update(kw)
    r = PendingCorosRun(**vals)
    db.add(r)
    db.commit()
    return r


def connect(db, status="connected"):
    db.add(CorosConnection(id=1, status=status))
    db.commit()


def mcp_confirm(shoe_id, label="480000000000000001", **kw):
    return mcp_server.confirm_coros_run(coros_activity_id=label, owned_shoe_id=shoe_id,
                                        date="2026-10-06", distance_km=12.53, **kw)


# --- one queue, two doors -------------------------------------------------------------

def test_confirming_via_claude_clears_the_app_inbox(db):
    s = shoe(db)
    p = pending(db)
    assert mcp_confirm(s.id)["success"] is True
    db.refresh(p)
    assert p.status == "confirmed" and p.resolved_at is not None
    assert inbox.list_pending(db) == []


def test_confirming_in_the_app_then_via_claude_does_not_double_log(db):
    s = shoe(db, 100.0)
    p = pending(db)
    inbox.confirm(db, p.id, owned_shoe_id=s.id)
    again = mcp_confirm(s.id)
    assert again["success"] is False and "already logged" in again["error"]
    db.refresh(s)
    assert db.query(Activity).count() == 1 and s.current_mileage == 112.53


def test_confirming_via_claude_then_in_the_app_does_not_double_log(db):
    s = shoe(db, 100.0)
    p = pending(db)
    mcp_confirm(s.id)
    out = inbox.confirm(db, p.id, owned_shoe_id=s.id)
    assert out["already_logged"] is True
    db.refresh(s)
    assert db.query(Activity).count() == 1 and s.current_mileage == 112.53


def test_run_logged_before_the_poller_saw_it_does_not_dangle_as_pending(db):
    s = shoe(db)
    db.add(Activity(source="coros", activity_type="Run", coros_activity_id="480000000000000001",
                    run_date=date(2026, 10, 6), distance_km=12.53))
    p = pending(db)                      # inbox row exists although the run is already logged
    db.commit()
    assert coros_svc.confirm_run(db, coros_activity_id=p.label_id, owned_shoe_id=s.id,
                                 run_date=p.run_date, distance_km=p.distance_km) is None
    db.refresh(p)
    assert p.status == "confirmed" and db.query(Activity).count() == 1


def test_dismissed_run_confirmed_via_claude_becomes_confirmed(db):
    s = shoe(db)
    p = pending(db)
    inbox.dismiss(db, p.id)
    assert mcp_confirm(s.id)["success"] is True
    db.refresh(p)
    assert p.status == "confirmed"


def test_confirm_without_an_inbox_row_still_works(db):
    s = shoe(db)
    assert mcp_confirm(s.id, label="999")["success"] is True      # e.g. logged from the connector flow
    assert db.query(Activity).count() == 1


# --- fetch_unsynced_coros_runs ----------------------------------------------------------

def test_fetch_returns_pending_queue_with_suggestions_and_detail(db):
    connect(db)
    s = shoe(db)
    pending(db, "1", suggested_shoe_id=s.id, suggestion_reason="because")
    pending(db, "2", status="dismissed")
    pending(db, "3", status="confirmed")
    out = mcp_server.fetch_unsynced_coros_runs(days_back=1)       # days_back is ignored
    assert out["success"] is True and out["coros_configured"] is True and "warning" not in out
    assert [r["coros_activity_id"] for r in out["runs"]] == ["1"]
    r = out["runs"][0]
    assert (r["date"], r["distance_km"], r["avg_pace"], r["avg_hr"]) == ("2026-10-06", 12.53, "4:12/km", 171)
    assert (r["elevation_gain_m"], r["moving_time_s"], r["elapsed_time_s"]) == (60.0, 3159, 3163)
    assert (r["avg_cadence"], r["calories"], r["training_load"], r["training_focus"]) == (186.0, 710.0, 113.0, "Base")
    assert r["suggested_shoe_id"] == s.id and r["suggestion_reason"] == "because"
    assert out["total_fetched"] == 1 and out["already_synced"] == 0


def test_fetch_output_feeds_confirm_unchanged(db):
    connect(db)
    s = shoe(db, 100.0)
    pending(db)
    r = mcp_server.fetch_unsynced_coros_runs()["runs"][0]
    out = mcp_server.confirm_coros_run(
        coros_activity_id=r["coros_activity_id"], owned_shoe_id=s.id, date=r["date"],
        distance_km=r["distance_km"], avg_pace=r["avg_pace"], avg_hr=r["avg_hr"],
        elevation_gain_m=r["elevation_gain_m"], moving_time_s=r["moving_time_s"],
        elapsed_time_s=r["elapsed_time_s"], avg_cadence=r["avg_cadence"], calories=r["calories"],
        training_load=r["training_load"], training_focus=r["training_focus"])
    assert out["success"] is True
    act = db.query(Activity).one()
    assert (act.elevation_gain_m, act.training_focus, act.avg_pace_s_per_km) == (60.0, "Base", 252)


@pytest.mark.parametrize("status,needle", [("reauth_required", "Reconnect"), ("disconnected", "Connect it")])
def test_fetch_warns_when_not_connected_but_still_lists_queued_runs(db, status, needle):
    connect(db, status)
    pending(db)
    out = mcp_server.fetch_unsynced_coros_runs()
    assert out["success"] is True and out["coros_configured"] is False
    assert len(out["runs"]) == 1 and needle in out["warning"]


def test_fetch_never_logs_anything(db):
    connect(db)
    shoe(db)
    pending(db)
    mcp_server.fetch_unsynced_coros_runs()
    assert db.query(Activity).count() == 0


# --- sync_coros_now (Son of Anton / Claude can run the app's Sync now) --------------------

class _FakeCoros:
    """Stands in for CorosMcpClient inside the poller: no runs, a fitness reading."""
    def __init__(self, *a, **k):
        from app.services.coros_mcp_client import CorosFitness
        self.fitness = CorosFitness(59.0, 97.0, 204, {"42.195": 8864})

    def list_runs(self, start, end):
        return []

    def fitness_overview(self):
        return self.fitness


@pytest.fixture()
def inline_thread(monkeypatch):
    """The test DB is in-memory SQLite (one connection per thread), so run the
    tool's worker-thread body on this thread."""
    async def run_inline(fn, *a, **k):
        return fn(*a, **k)
    monkeypatch.setattr(asyncio, "to_thread", run_inline)


def test_sync_coros_now_runs_the_manual_sync_and_saves_fitness(db, monkeypatch, inline_thread):
    from app.services import best_efforts as be, coros_poller
    monkeypatch.setattr(coros_poller, "CorosMcpClient", _FakeCoros)
    monkeypatch.setattr(be, "scan_coros", lambda db, client: be.ScanSummary())
    connect(db)
    out = asyncio.run(mcp_server.sync_coros_now())
    assert out["success"] is True and out["queued"] == 0 and out["fitness_recorded"] is True
    assert out["fitness"]["vo2max"] == 59.0 and out["fitness"]["threshold_pace"] == "3:24/km"
    assert db.get(CorosSyncState, 1).last_trigger == "manual"
    again = asyncio.run(mcp_server.sync_coros_now())
    assert again["fitness_recorded"] is False                      # unchanged → not re-saved
    assert db.query(Activity).count() == 0                         # never logs a run


def test_sync_coros_now_not_connected_is_a_clean_failure(db, inline_thread):
    out = asyncio.run(mcp_server.sync_coros_now())
    assert out == {"success": False, "error": "COROS isn't connected. Connect it in Settings → Sync."}


# --- get_coros_sync_status ----------------------------------------------------------------

def test_status_connected_reports_poller_state(db):
    connect(db)
    pending(db)
    st = CorosSyncState(id=1, runs_found=1, last_error="COROS unreachable (ConnectionError)")
    db.add(st)
    db.commit()
    out = mcp_server.get_coros_sync_status()
    assert out["connection_status"] == "connected" and out["coros_configured"] is True
    assert out["pending_count"] == 1 and out["last_error"].startswith("COROS unreachable")
    assert "1 run(s) waiting" in out["message"] and "last poll failed" in out["message"]
    assert out["poll_interval_min"] == 15


def test_status_reauth_and_disconnected_messages(db):
    connect(db, "reauth_required")
    out = mcp_server.get_coros_sync_status()
    assert out["coros_configured"] is False and "reconnected" in out["message"]
    db.get(CorosConnection, 1).status = "disconnected"
    db.commit()
    assert "not connected" in mcp_server.get_coros_sync_status()["message"]


def test_status_server_not_configured(db, monkeypatch):
    monkeypatch.delenv("COROS_TOKEN_KEY")
    out = mcp_server.get_coros_sync_status()
    assert out["coros_configured"] is False and "COROS_TOKEN_KEY" in out["message"]


def test_status_never_connected_is_not_an_error(db):
    out = mcp_server.get_coros_sync_status()
    assert out["connection_status"] == "disconnected" and out["pending_count"] == 0
    assert out["last_success_at"] is None


# --- the agent prompt -----------------------------------------------------------------------

def test_prompt_uses_the_queue_not_the_connector_for_logging():
    text = mcp_server.sync_coros_runs()
    assert "fetch_unsynced_coros_runs" in text
    assert "querySportRecords" not in text and "Step 1b" not in text
    assert "do NOT call getActivityDetail" in text
    assert "suggested_shoe_id" in text and "confirm_coros_run" in text
