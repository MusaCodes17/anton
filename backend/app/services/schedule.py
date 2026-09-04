"""
Nightly scrape scheduler (R4.1; UI-configurable since #7).

Wraps an APScheduler AsyncIOScheduler that fires run_scrape_job on a
configurable cron schedule. The scheduler lives inside the single uvicorn
worker (INV-9 — the single-process assumption is not relaxed). The existing
in-memory scrape lock guards against overlap with manually-triggered scrapes
(design_decisions D4 — refuse, not queue). APScheduler's max_instances=1
additionally prevents the scheduler from stacking the job with itself if a
scheduled run overruns its slot.

Configuration precedence (#7): **DB row → env var → hardcoded default**, per
field. The `AppSettings` keys `scrape_schedule_enabled` / `scrape_schedule_cron`
are the UI-writable source of truth; the env vars `SCRAPE_SCHEDULE_ENABLED` /
`SCRAPE_SCHEDULE_CRON` remain a working fallback so the schedule can still be
governed from the server if the DB/UI is ever wedged. Changes apply at runtime
(apply_config mutates the live scheduler) — no restart, safe because INV-9
guarantees exactly one process holds this singleton.

Env vars (fallback only):
  SCRAPE_SCHEDULE_ENABLED  "true" / "false"   (default "false" — opt-in)
  SCRAPE_SCHEDULE_CRON     crontab string      (default "0 3 * * *" = 3 am daily)

Timezone is fixed to America/Toronto (the runner's local zone); the cron
expression is interpreted in that zone regardless of the server's system TZ.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.services import settings as settings_svc

logger = logging.getLogger(__name__)

_TZ = pytz.timezone("America/Toronto")
_JOB_ID = "nightly_scrape"

# AppSettings keys (UI-writable source of truth; see module docstring).
_KEY_ENABLED = "scrape_schedule_enabled"
_KEY_CRON = "scrape_schedule_cron"

_DEFAULT_CRON = "0 3 * * *"

# Module-level singleton — one scheduler per process (INV-9).
_scheduler: Optional[AsyncIOScheduler] = None


def _resolve(db: Session, key: str, env_var: str, default: str) -> tuple[str, str]:
    """Resolve one config value DB → env → default, returning (value, source)."""
    db_val = settings_svc.get_setting(db, key)
    if db_val is not None:
        return db_val, "db"
    env_val = os.getenv(env_var)
    if env_val is not None:
        return env_val, "env"
    return default, "default"


def get_config(db: Session) -> dict:
    """
    Resolved schedule config with provenance.

    Returns:
        enabled  bool      — whether scheduled scraping is on
        cron     str       — the resolved cron expression
        source   dict      — {"enabled": "db"|"env"|"default",
                              "cron":    "db"|"env"|"default"} so a reader can
                             see which layer each value came from.
    """
    enabled_raw, enabled_src = _resolve(db, _KEY_ENABLED, "SCRAPE_SCHEDULE_ENABLED", "false")
    cron, cron_src = _resolve(db, _KEY_CRON, "SCRAPE_SCHEDULE_CRON", _DEFAULT_CRON)
    return {
        "enabled": enabled_raw.strip().lower() == "true",
        "cron": cron,
        "source": {"enabled": enabled_src, "cron": cron_src},
    }


def validate_cron(expr: str) -> CronTrigger:
    """
    Build (and thereby validate) a CronTrigger from a crontab string.

    Returns the trigger for callers that want it; raises ValueError on any
    malformed or out-of-range expression (e.g. "0 99 * * *"). A bad cron must
    never reach storage — the write endpoint and apply_config both gate on this
    so the job can't silently fail to register.
    """
    try:
        return CronTrigger.from_crontab(expr, timezone=_TZ)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid cron expression {expr!r}: {exc}")


def _trigger_to_crontab(trigger) -> Optional[str]:
    """
    Reconstruct a "M H D M DOW" crontab string from a live CronTrigger, so
    get_status can report what is *actually* scheduled (applied_cron) rather
    than only what config resolves to. None if the trigger isn't a CronTrigger.
    """
    if not isinstance(trigger, CronTrigger):
        return None
    parts = {f.name: str(f) for f in trigger.fields}
    return " ".join(
        parts.get(name, "*") for name in ("minute", "hour", "day", "month", "day_of_week")
    )


async def _run_scheduled_scrape() -> None:
    """
    Entry point fired by the scheduler.

    Tries to acquire the process-wide scrape lock (D4 — refuse not queue).
    If a manual or background scrape is already running, logs and skips — the
    next scheduled slot will try again. run_scrape_job's finally always
    releases the lock, so acquisition here and release there are balanced.
    """
    from app.scrape_runner import run_scrape_job
    from app.scrapers.lock import try_acquire_scrape_lock

    if not try_acquire_scrape_lock():
        logger.info("Scheduled scrape skipped — a scrape is already in progress")
        return
    logger.info("Scheduled scrape starting")
    await run_scrape_job(trigger="scheduled")


def apply_config(db: Session) -> dict:
    """
    Reconcile the live scheduler with the resolved config (register / reschedule
    / remove the job). The single code path both boot and runtime edits go
    through, so a status read can never disagree with the live job for long.

    No-op-safe: returns quietly if the scheduler hasn't been created yet, tolerates
    the job being absent, and treats an invalid resolved cron (only reachable via a
    bad *env* fallback — the write path validates before storage) as "leave the
    schedule inactive" rather than crashing boot (graceful degradation, §4.5).

    Returns the post-apply get_status(db) dict.
    """
    if _scheduler is None:
        return get_status(db)

    cfg = get_config(db)
    existing = _scheduler.get_job(_JOB_ID)

    if cfg["enabled"]:
        try:
            trigger = validate_cron(cfg["cron"])
        except ValueError:
            logger.error(
                "Invalid cron in resolved config (%r) — leaving schedule inactive",
                cfg["cron"],
            )
            if existing:
                _scheduler.remove_job(_JOB_ID)
            return get_status(db)
        _scheduler.add_job(
            _run_scheduled_scrape,
            trigger,
            id=_JOB_ID,
            coalesce=True,        # misfire → run once, not N times
            max_instances=1,      # never overlap two scheduled runs
            replace_existing=True,  # register or reschedule in one call
        )
        logger.info(f"Scheduled scraping active: cron={cfg['cron']!r} (America/Toronto)")
    elif existing:
        _scheduler.remove_job(_JOB_ID)
        logger.info("Scheduled scraping disabled — job removed")

    return get_status(db)


def start(db: Session) -> None:
    """
    Create and start the AsyncIOScheduler, then apply the resolved config.

    Called from the app lifespan on startup with a short-lived read-only
    session. The scheduler always starts (so get_status works even when
    disabled); apply_config decides whether a job is registered — boot and
    runtime edits share that one path.
    """
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=_TZ)
    apply_config(db)
    _scheduler.start()

    cfg = get_config(db)
    if not cfg["enabled"]:
        logger.info("Scheduled scraping disabled at boot")


def shutdown() -> None:
    """Stop the scheduler. Called from the app lifespan on teardown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None


def get_status(db: Session) -> dict:
    """
    Current schedule state for the admin endpoint and the Settings UI.

    Returns:
        enabled           bool     — resolved enabled flag (DB → env → default)
        cron              str      — resolved cron expression (the *intended* schedule)
        applied_cron      str|None — the crontab of the job actually registered on the
                                     live scheduler; diverges from `cron` only if a config
                                     change hasn't been applied yet (then it's visible here,
                                     not silent)
        next_run_utc      str|None — ISO datetime of the next fire, or null
        scheduler_running bool     — whether the APScheduler instance is alive
        source            dict     — per-field provenance from get_config
    """
    cfg = get_config(db)
    running = _scheduler is not None and _scheduler.running

    next_run: Optional[str] = None
    applied_cron: Optional[str] = None
    if _scheduler is not None:
        job = _scheduler.get_job(_JOB_ID)
        if job:
            applied_cron = _trigger_to_crontab(job.trigger)
            # next_run_time is only assigned once the scheduler is running; a job
            # added while it's stopped (or pending at boot) hasn't got it yet.
            nrt = getattr(job, "next_run_time", None)
            if nrt:
                next_run = nrt.isoformat()

    return {
        "enabled": cfg["enabled"],
        "cron": cfg["cron"],
        "applied_cron": applied_cron,
        "next_run_utc": next_run,
        "scheduler_running": running,
        "source": cfg["source"],
    }
