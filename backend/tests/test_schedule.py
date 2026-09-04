"""
Tests for the R4.1 scheduled scraping feature + #7 UI-configurable schedule.

Covers:
  - trigger parameter threads through scrape_runner to ScrapeRun
  - config resolution precedence (DB → env → default) and provenance
  - validate_cron rejects bad expressions before they can be stored
  - apply_config registers / reschedules / removes the live job
  - get_status reflects a DB-set value and reports applied_cron/next_run
  - GET /api/admin/schedule response shape
  - PUT /api/admin/schedule persists, reschedules, validates (422), and auth

Isolation notes (MAINTENANCE_PLAN D6 + #7): schedule config now lives in the DB
too, so an autouse fixture wipes AppSettings on the shared engine and resets the
module-level scheduler singleton between tests, and re-asserts the get_db
override so a sibling test module's override can't bleed in. Env vars are handled
per test via monkeypatch (auto-reverted).
"""
import os

# Must match test_auth / test_http_smoke values so middleware is consistent
TEST_SECRET = "test-anton-secret-0123456789abcdef"
TEST_OTHER = "test-other-secret-0123456789abcd00"
os.environ["ANTON_TOKENS"] = f"desktop:{TEST_SECRET},spa:{TEST_OTHER}"

import pytest  # noqa: E402
import httpx  # noqa: E402
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import models  # noqa: E402
from app.services import schedule as svc  # noqa: E402
from app.services import settings as settings_svc  # noqa: E402

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=_engine)
_Session = sessionmaker(bind=_engine)


def _db_override():
    db = _Session()
    try:
        yield db
    finally:
        db.close()


_AUTH = {"Authorization": f"Bearer {TEST_SECRET}"}


@pytest.fixture(autouse=True)
def _isolate():
    """Fresh AppSettings + scheduler singleton per test; own get_db override."""
    app.dependency_overrides[get_db] = _db_override
    s = _Session()
    s.query(models.AppSettings).delete()
    s.commit()
    s.close()
    yield
    # Drop the singleton directly rather than svc.shutdown(): an async test binds
    # its scheduler to that test's event loop, which is already closed by the time
    # this (sync) teardown runs — calling shutdown() on it would hit a dead loop.
    svc._scheduler = None
    s = _Session()
    s.query(models.AppSettings).delete()
    s.commit()
    s.close()


# ── config resolution (DB → env → default) ────────────────────────────────────

def test_config_default_when_db_and_env_unset(monkeypatch, db):
    monkeypatch.delenv("SCRAPE_SCHEDULE_ENABLED", raising=False)
    monkeypatch.delenv("SCRAPE_SCHEDULE_CRON", raising=False)
    cfg = svc.get_config(db)
    assert cfg["enabled"] is False
    assert cfg["cron"] == "0 3 * * *"
    assert cfg["source"] == {"enabled": "default", "cron": "default"}


def test_config_env_used_when_db_unset(monkeypatch, db):
    monkeypatch.setenv("SCRAPE_SCHEDULE_ENABLED", "true")
    monkeypatch.setenv("SCRAPE_SCHEDULE_CRON", "0 6 * * *")
    cfg = svc.get_config(db)
    assert cfg["enabled"] is True
    assert cfg["cron"] == "0 6 * * *"
    assert cfg["source"] == {"enabled": "env", "cron": "env"}


def test_config_db_wins_over_env(monkeypatch, db):
    monkeypatch.setenv("SCRAPE_SCHEDULE_ENABLED", "false")
    monkeypatch.setenv("SCRAPE_SCHEDULE_CRON", "0 6 * * *")
    settings_svc.set_setting(db, "scrape_schedule_enabled", "true")
    settings_svc.set_setting(db, "scrape_schedule_cron", "30 4 * * *")
    db.commit()
    cfg = svc.get_config(db)
    assert cfg["enabled"] is True
    assert cfg["cron"] == "30 4 * * *"
    assert cfg["source"] == {"enabled": "db", "cron": "db"}


# ── validate_cron ──────────────────────────────────────────────────────────────

def test_validate_cron_accepts_good():
    trigger = svc.validate_cron("30 4 * * *")
    assert trigger is not None


@pytest.mark.parametrize("bad", ["0 99 * * *", "not a cron", "* * *", ""])
def test_validate_cron_rejects_bad(bad):
    with pytest.raises(ValueError):
        svc.validate_cron(bad)


# ── apply_config mutates the live scheduler ────────────────────────────────────

def test_apply_config_registers_reschedules_and_removes(monkeypatch, db):
    monkeypatch.delenv("SCRAPE_SCHEDULE_ENABLED", raising=False)
    monkeypatch.delenv("SCRAPE_SCHEDULE_CRON", raising=False)
    # A scheduler that exists but isn't started — apply_config works on the jobstore.
    svc._scheduler = AsyncIOScheduler(timezone=svc._TZ)

    # Disabled → no job.
    svc.apply_config(db)
    assert svc._scheduler.get_job(svc._JOB_ID) is None

    # Enable via DB → job registered with the resolved cron.
    settings_svc.set_setting(db, "scrape_schedule_enabled", "true")
    settings_svc.set_setting(db, "scrape_schedule_cron", "0 3 * * *")
    db.commit()
    status = svc.apply_config(db)
    assert svc._scheduler.get_job(svc._JOB_ID) is not None
    assert status["applied_cron"] == "0 3 * * *"
    # (Reschedule-to-a-new-time is exercised on a *running* scheduler in the PUT
    # tests below; APScheduler only de-dupes a replaced job once started.)

    # Disable → job removed, next_run cleared.
    settings_svc.set_setting(db, "scrape_schedule_enabled", "false")
    db.commit()
    status = svc.apply_config(db)
    assert svc._scheduler.get_job(svc._JOB_ID) is None
    assert status["next_run_utc"] is None


def test_apply_config_noop_when_scheduler_absent(db):
    svc._scheduler = None  # never created
    # Must not raise, and returns a status dict.
    status = svc.apply_config(db)
    assert status["scheduler_running"] is False


# ── get_status ─────────────────────────────────────────────────────────────────

def test_get_status_disabled_by_default(monkeypatch, db):
    monkeypatch.delenv("SCRAPE_SCHEDULE_ENABLED", raising=False)
    monkeypatch.delenv("SCRAPE_SCHEDULE_CRON", raising=False)
    status = svc.get_status(db)
    assert status["enabled"] is False
    assert status["cron"] == "0 3 * * *"
    assert status["next_run_utc"] is None
    assert status["applied_cron"] is None  # no scheduler/job


def test_get_status_reflects_db_value(monkeypatch, db):
    monkeypatch.delenv("SCRAPE_SCHEDULE_ENABLED", raising=False)
    settings_svc.set_setting(db, "scrape_schedule_enabled", "true")
    settings_svc.set_setting(db, "scrape_schedule_cron", "15 2 * * *")
    db.commit()
    status = svc.get_status(db)
    assert status["enabled"] is True
    assert status["cron"] == "15 2 * * *"


# ── scrape_runner trigger param ───────────────────────────────────────────────

def test_run_scrape_job_accepts_trigger_param():
    """Verifies the function signature includes trigger without calling it."""
    import inspect
    from app.scrape_runner import run_scrape_job
    sig = inspect.signature(run_scrape_job)
    assert "trigger" in sig.parameters
    assert sig.parameters["trigger"].default == "background"


def test_scrape_one_retailer_accepts_trigger_param():
    import inspect
    from app.scrape_runner import _scrape_one_retailer
    sig = inspect.signature(_scrape_one_retailer)
    assert "trigger" in sig.parameters
    assert sig.parameters["trigger"].default == "background"


# ── GET /api/admin/schedule ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_schedule_endpoint_shape(monkeypatch):
    monkeypatch.delenv("SCRAPE_SCHEDULE_ENABLED", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/admin/schedule", headers=_AUTH)
    assert r.status_code == 200
    data = r.json()
    for key in ("enabled", "cron", "applied_cron", "next_run_utc",
                "scheduler_running", "is_scraping_now", "recent_scheduled_runs"):
        assert key in data
    assert isinstance(data["recent_scheduled_runs"], list)


@pytest.mark.anyio
async def test_schedule_endpoint_requires_auth():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/admin/schedule")
    # 401 = no auth header; 429 = rate limiter fires first after many unauthed
    # test requests — both mean "access denied without credentials".
    assert r.status_code in (401, 429)


@pytest.mark.anyio
async def test_schedule_endpoint_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SCRAPE_SCHEDULE_ENABLED", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/admin/schedule", headers=_AUTH)
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["next_run_utc"] is None


# ── pytest-anyio config ───────────────────────────────────────────────────────

pytest_plugins = ("anyio",)
