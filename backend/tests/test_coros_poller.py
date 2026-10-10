"""COROS direct sync §4 — poller + pending queue.

Rules under test (not plumbing): exactly-once queueing across overlapping
lookbacks, dismissed/confirmed runs never resurrect, already-logged runs are not
queued (by label id AND by the date+distance fallback), the poller never touches
runs or mileage (INV-1/INV-9), failures are recorded honestly and never raised,
auth failure stops polling, the lookback self-heals after downtime.
"""
import dataclasses
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("ANTON_TOKENS", "desktop:test-poller-token-0123456789abcdef")

import pytest
import requests

from app.models.models import (
    Activity, AthleteMetric, CorosConnection, CorosSyncState, OwnedShoe, PendingCorosRun, ShoeRun,
)
from app.services import coros_poller as poller
from app.services.coros_connection import CorosAuthError
from app.services.coros_mcp_client import (
    CorosContractError, parse_fitness_overview, parse_sport_records,
)

FIX = Path(__file__).parent / "fixtures" / "coros" / "query_sport_records.json"
RUNS = parse_sport_records(json.loads(FIX.read_text())["result"]["content"][0]["text"])
TODAY = date(2026, 10, 7)
FITNESS = parse_fitness_overview(json.loads(
    (FIX.parent / "fitness_overview.json").read_text())["result"]["content"][0]["text"])


class FakeClient:
    def __init__(self, runs=RUNS):
        self.runs = runs
        self.list_calls = []          # (start, end)
        self.fetched = []             # label ids whose detail was fetched
        self.list_exc = None
        self.fetch_exc = {}           # label_id -> exception
        self.on_fetch = None
        self.fitness = FITNESS
        self.fitness_calls = 0
        self.fitness_exc = None

    def list_runs(self, start, end):
        self.list_calls.append((start, end))
        if self.list_exc:
            raise self.list_exc
        return self.runs

    def fitness_overview(self):
        self.fitness_calls += 1
        if self.fitness_exc:
            raise self.fitness_exc
        return self.fitness

    def fetch_run(self, run):
        if self.on_fetch:
            self.on_fetch(run)
        if run.label_id in self.fetch_exc:
            raise self.fetch_exc[run.label_id]
        self.fetched.append(run.label_id)
        return dataclasses.replace(run, has_detail=True, elapsed_time_s=run.moving_time_s + 4,
                                   elevation_gain_m=12.0, avg_cadence=180.0, training_load=90.0,
                                   training_focus="Base")


@pytest.fixture(autouse=True)
def _release_lock():
    poller._fitness_checked_on = None
    yield
    if poller._tick_lock.locked():
        poller._tick_lock.release()


@pytest.fixture()
def connected(db):
    db.add(CorosConnection(id=1, status="connected"))
    db.commit()
    return db


def tick(db, client, **kw):
    return poller.run_tick(db, client=client, today=TODAY, **kw)


# --- queueing & exactly-once ------------------------------------------------------

def test_not_connected_does_nothing(db):
    c = FakeClient()
    r = tick(db, c)
    assert r.skipped == "not_connected" and c.list_calls == []
    assert db.get(CorosSyncState, 1) is None


def test_first_tick_queues_every_run_with_detail_and_looks_back_14_days(connected):
    c = FakeClient()
    r = tick(connected, c)
    assert (r.found, r.queued, r.ok) == (14, 14, True)
    assert c.list_calls == [(TODAY - timedelta(days=14), TODAY)]
    row = connected.query(PendingCorosRun).filter_by(label_id="480858305181286402").one()
    assert row.status == "pending" and row.run_date == date(2026, 10, 6)
    assert row.elapsed_time_s == row.moving_time_s + 4 and row.training_focus == "Base"
    assert row.suggested_shoe_id is None
    st = connected.get(CorosSyncState, 1)
    assert st.last_success_at is not None and st.last_error is None and st.runs_found == 14


def test_overlapping_lookback_queues_nothing_twice(connected):
    c = FakeClient()
    tick(connected, c)
    c2 = FakeClient()
    r = tick(connected, c2)
    assert r.queued == 0 and c2.fetched == []          # not even detail re-fetched
    assert connected.query(PendingCorosRun).count() == 14
    assert connected.get(CorosSyncState, 1).runs_found == 0


def test_dismissed_and_confirmed_runs_never_resurrect(connected):
    tick(connected, FakeClient())
    for i, row in enumerate(connected.query(PendingCorosRun).all()):
        row.status = "dismissed" if i % 2 else "confirmed"
    connected.commit()
    r = tick(connected, FakeClient())
    assert r.queued == 0 and connected.query(PendingCorosRun).filter_by(status="pending").count() == 0


def test_already_logged_by_label_id_is_skipped(connected):
    connected.add(Activity(source="coros", activity_type="Run", coros_activity_id="480858305181286402",
                           run_date=date(2026, 10, 6), distance_km=12.53))
    connected.commit()
    r = tick(connected, FakeClient())
    assert r.queued == 13
    assert connected.query(PendingCorosRun).filter_by(label_id="480858305181286402").count() == 0


def test_already_logged_by_date_and_distance_fallback_is_skipped(connected):
    # logged earlier via the Claude workflow / manually, without the COROS id; 0.05 km off
    connected.add(Activity(source="manual", activity_type="Run", run_date=date(2026, 10, 4), distance_km=14.24))
    connected.commit()
    tick(connected, FakeClient())
    assert connected.query(PendingCorosRun).filter_by(label_id="480809994315399172").count() == 0


def test_lost_unique_race_is_a_silent_noop(connected):
    c = FakeClient(RUNS[:1])

    def sneak_in(run):  # another writer queues the same label between our check and insert
        connected.add(PendingCorosRun(label_id=run.label_id, sport_type=100, run_date=run.run_date,
                                      distance_km=1, moving_time_s=1, avg_pace_s_per_km=300,
                                      start_timestamp=1, end_timestamp=2))
        connected.commit()
    c.on_fetch = sneak_in
    r = tick(connected, c)
    assert r.queued == 0 and r.ok
    assert connected.query(PendingCorosRun).count() == 1


def test_queued_runs_carry_the_shoe_suggestion(connected):
    daily = OwnedShoe(brand="B", model="Daily", shoe_type="daily_trainer", starting_mileage=0,
                      current_mileage=50, status="active")
    connected.add(daily)
    connected.commit()
    tick(connected, FakeClient())
    easy = connected.query(PendingCorosRun).filter_by(label_id="480779046928548143").one()  # 6:03/km, 10.26 km
    assert easy.suggested_shoe_id == daily.id and "daily_trainer" in easy.suggestion_reason
    fast = connected.query(PendingCorosRun).filter_by(label_id="480858305181286402").one()  # 4:12/km, 12.53 km
    assert fast.suggested_shoe_id == daily.id  # conflict -> union -> the only active candidate


# --- invariants -------------------------------------------------------------------

def test_poller_never_writes_runs_or_mileage(connected):
    shoe = OwnedShoe(brand="B", model="M", starting_mileage=100, current_mileage=123.4, status="active")
    connected.add(shoe)
    connected.commit()
    tick(connected, FakeClient())
    connected.expire_all()
    assert connected.query(Activity).count() == 0 and connected.query(ShoeRun).count() == 0
    assert connected.get(OwnedShoe, shoe.id).current_mileage == 123.4


# --- fitness snapshots (R8.4.1) ------------------------------------------------------

def test_first_tick_saves_a_fitness_snapshot_without_confirmation(connected):
    r = tick(connected, FakeClient())
    assert r.fitness_recorded is True
    snap = connected.query(AthleteMetric).one()
    assert (snap.vo2max, snap.running_level, snap.threshold_pace_s_per_km) == (59.0, 97.0, 204)
    assert snap.race_predictions["42.195"] == 8864


def test_quiet_scheduled_tick_does_not_refetch_fitness_the_same_day(connected):
    tick(connected, FakeClient())
    c = FakeClient()                                  # same runs: nothing new queued
    r = tick(connected, c)
    assert r.queued == 0 and c.fitness_calls == 0 and r.fitness_recorded is False


def test_new_day_fetches_fitness_as_a_fallback(connected):
    tick(connected, FakeClient())
    c = FakeClient()
    poller.run_tick(connected, client=c, today=TODAY + timedelta(days=1))
    assert c.fitness_calls == 1


def test_a_new_run_refetches_fitness_the_same_day(connected):
    tick(connected, FakeClient(RUNS[1:]))
    c = FakeClient()
    r = tick(connected, c)
    assert r.queued == 1 and c.fitness_calls == 1


def test_manual_sync_always_fetches_fitness(connected):
    tick(connected, FakeClient())
    c = FakeClient()
    tick(connected, c, trigger="manual")
    assert c.fitness_calls == 1


def test_unchanged_fitness_is_not_saved_again_and_a_change_is(connected):
    tick(connected, FakeClient())
    r = tick(connected, FakeClient(), trigger="manual")
    assert r.fitness_recorded is False and connected.query(AthleteMetric).count() == 1
    c = FakeClient()
    c.fitness = dataclasses.replace(FITNESS, vo2max=60.0)
    assert tick(connected, c, trigger="manual").fitness_recorded is True
    assert connected.query(AthleteMetric).count() == 2


def test_fitness_failure_never_fails_the_poll(connected):
    c = FakeClient()
    c.fitness_exc = CorosContractError("VO2max reworded")
    r = tick(connected, c)
    assert r.ok and r.queued == 14 and r.fitness_recorded is False
    assert connected.query(AthleteMetric).count() == 0
    assert connected.get(CorosSyncState, 1).last_error is None
    c2 = FakeClient()
    tick(connected, c2)                               # the day counts as checked: no retry storm
    assert c2.fitness_calls == 0


def test_fitness_auth_failure_marks_reauth(connected):
    c = FakeClient()
    c.fitness_exc = CorosAuthError("401")
    tick(connected, c)
    assert connected.get(CorosConnection, 1).status == "reauth_required"


def test_failed_poll_skips_fitness(connected):
    c = FakeClient()
    c.list_exc = requests.ConnectionError("down")
    tick(connected, c, trigger="manual")
    assert c.fitness_calls == 0


# --- failure behaviour --------------------------------------------------------------

def test_network_failure_is_recorded_not_raised_and_not_a_success(connected):
    c = FakeClient()
    c.list_exc = requests.ConnectionError("down")
    r = tick(connected, c)
    assert not r.ok and r.queued == 0
    st = connected.get(CorosSyncState, 1)
    assert st.last_success_at is None and "unreachable" in st.last_error
    assert st.last_attempt_at is not None
    # next tick recovers
    assert tick(connected, FakeClient()).queued == 14
    assert connected.get(CorosSyncState, 1).last_error is None


def test_auth_failure_marks_reauth_and_polling_stops(connected):
    c = FakeClient()
    c.list_exc = CorosAuthError("401")
    r = tick(connected, c)
    assert not r.ok and "reconnect" in r.errors[0]
    assert connected.get(CorosConnection, 1).status == "reauth_required"
    c2 = FakeClient()
    assert tick(connected, c2).skipped == "not_connected" and c2.list_calls == []


def test_one_bad_detail_does_not_abort_the_rest_or_count_as_success(connected):
    c = FakeClient()
    c.fetch_exc["480858305181286402"] = CorosContractError("Workout Time missing")
    r = tick(connected, c)
    assert r.queued == 13 and not r.ok
    st = connected.get(CorosSyncState, 1)
    assert st.last_success_at is None and "480858305181286402" in st.last_error
    # the failed run is retried on the next tick (it was never queued)
    assert tick(connected, FakeClient()).queued == 1


def test_concurrent_tick_is_refused_not_queued(connected):
    poller._tick_lock.acquire()
    c = FakeClient()
    assert tick(connected, c).skipped == "already_running" and c.list_calls == []


# --- lookback ---------------------------------------------------------------------

def _set_last_success(db, days_ago):
    st = poller._state(db)
    st.last_success_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    db.commit()


def test_lookback_windows(connected):
    assert poller._window(connected, TODAY) == (TODAY - timedelta(days=14), TODAY)   # never synced
    st = poller._state(connected)
    st.last_success_at = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)           # yesterday
    connected.commit()
    assert poller._window(connected, TODAY)[0] == TODAY - timedelta(days=3)          # configured floor
    st.last_success_at = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)           # 10 days ago
    connected.commit()
    assert poller._window(connected, TODAY)[0] == TODAY - timedelta(days=11)         # covers the gap
    st.last_success_at = datetime(2026, 6, 1, tzinfo=timezone.utc)                   # long outage
    connected.commit()
    assert poller._window(connected, TODAY)[0] == TODAY - timedelta(days=30)         # capped


def test_lookback_env_override(connected, monkeypatch):
    monkeypatch.setenv("COROS_POLL_LOOKBACK_DAYS", "5")
    st = poller._state(connected)
    st.last_success_at = datetime(2026, 10, 7, 1, 0, tzinfo=timezone.utc)
    connected.commit()
    assert poller._window(connected, TODAY)[0] == TODAY - timedelta(days=5)


# --- scheduler integration --------------------------------------------------------

def test_poll_job_registers_on_the_shared_scheduler_and_respects_zero(monkeypatch):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.services import schedule as sched
    monkeypatch.setattr(sched, "_scheduler", AsyncIOScheduler())
    sched.apply_coros_poll()
    job = sched._scheduler.get_job("coros_poll")
    assert job is not None and job.trigger.interval == timedelta(minutes=15)
    monkeypatch.setenv("COROS_POLL_INTERVAL_MIN", "0")
    sched.apply_coros_poll()
    assert sched._scheduler.get_job("coros_poll") is None
    monkeypatch.setenv("COROS_POLL_INTERVAL_MIN", "5")
    sched.apply_coros_poll()
    assert sched._scheduler.get_job("coros_poll").trigger.interval == timedelta(minutes=5)


# --- HTTP -------------------------------------------------------------------------

@pytest.fixture()
def http(monkeypatch):
    import asyncio
    import httpx
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.database import Base, get_db
    from app.main import app
    from app.services.rate_limit import auth_failure_limiter

    auth_failure_limiter._buckets.clear()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    S = sessionmaker(bind=engine)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()

    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db
    pairs = dict(p.split(":", 1) for p in os.environ["ANTON_TOKENS"].split(","))

    def call(method, path, auth=True):
        headers = {"Authorization": f"Bearer {pairs['desktop']}"} if auth else {}

        async def _go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
                return await c.request(method, path, headers=headers)
        return asyncio.run(_go())

    call.session = S
    yield call
    if prev is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = prev


def test_sync_endpoint_requires_auth(http):
    assert http("POST", "/api/coros/sync", auth=False).status_code == 401


def test_sync_endpoint_409_when_not_connected(http):
    assert http("POST", "/api/coros/sync").status_code == 409


def test_sync_endpoint_runs_a_tick_and_status_reports_it(http, monkeypatch):
    s = http.session()
    s.add(CorosConnection(id=1, status="connected"))
    s.commit()
    s.close()
    monkeypatch.setattr(poller, "CorosMcpClient", lambda *a, **k: FakeClient(RUNS[:3]))
    r = http("POST", "/api/coros/sync")
    assert r.status_code == 200 and r.json() == {"ok": True, "found": 3, "queued": 3,
                                       "fitness_recorded": True, "errors": []}
    st = http("GET", "/api/coros/status").json()
    assert st["sync"]["pending_count"] == 3 and st["sync"]["last_trigger"] == "manual"
    assert st["sync"]["last_error"] is None


def test_poll_stores_label_and_rounded_coordinates_on_the_pending_row(connected):
    tick(connected, FakeClient())
    row = connected.query(PendingCorosRun).filter_by(label_id="480858305181286402").one()
    assert row.location_label == "Montreal Run"
    assert (row.start_lat, row.start_lng) == (45.502, -73.567)   # 45.501689, -73.567256 rounded to 3 dp
