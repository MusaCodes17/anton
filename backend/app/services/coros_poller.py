"""
COROS poller — pulls new runs into the pending queue (COROS direct sync §4).

Job: each tick lists recent COROS runs, drops anything already queued or already
logged, prefetches detail + a shoe suggestion for the rest, and inserts them as
`pending_coros_runs`. **It never writes runs, attributions or mileage** (INV-1,
INV-9, C9): the only tables it writes are `pending_coros_runs`,
`coros_sync_state`, and — after polling — the derived best-effort tables for
runs the runner has already confirmed (R8.2, services/best_efforts) and an
`athlete_metrics` fitness snapshot when COROS's reading changed (R8.4.1,
services/fitness). Logging stays the runner's confirm, through the one writer.

Dedup (exactly-once across overlapping lookbacks and restarts):
1. `pending_coros_runs.label_id` is UNIQUE and rows are never deleted by the
   poller, so a dismissed/confirmed run is never re-queued.
2. Already logged (via Claude, Strava-era manual entry, ...) is detected by the
   established `coros.is_already_logged` rule: `activities.coros_activity_id ==
   label_id`, else same date + distance within 0.1 km.

Lookback: configured default 3 days (late watch syncs), but widened to cover the
gap since the last successful tick (capped at 30 days) so an outage, a
disconnect or a long downtime self-heals; the very first sync looks back 14 days.

Failure behaviour: `run_tick` NEVER raises. Auth failure marks the connection
`reauth_required` (polling then stops by itself — ticks no-op unless connected).
Network/contract failures are recorded in `coros_sync_state.last_error` and the
next tick simply tries again (no in-tick retry storm; the client already did its
bounded retries). One run's bad detail doesn't abort the others.

Concurrency: one tick at a time (`_tick_lock`, non-blocking — a manual sync during
a scheduled tick reports "already running" rather than queueing). Token refresh is
separately serialized in coros_connection. Each tick owns its DB session
(one session per thread) — see `run_scheduled_tick`.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import CorosSyncState, PendingCorosRun
from app.services import best_efforts as best_efforts_svc
from app.services import coros as coros_svc
from app.services import coros_connection as conn
from app.services import fitness as fitness_svc
from app.services.coros_mcp_client import (
    CorosApiError, CorosContractError, CorosMcpClient, CorosRun,
)
from app.services.coros_suggestion import suggest_shoe
from app.utils.location import round_coord

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Toronto")
DEFAULT_INTERVAL_MIN = 15
DEFAULT_LOOKBACK_DAYS = 3
FIRST_SYNC_LOOKBACK_DAYS = 14
MAX_LOOKBACK_DAYS = 30
_STATE_ID = 1

_tick_lock = threading.Lock()

# R8.4.1: the Toronto date of the last fitness fetch, so a quiet day still gets
# one. In-memory on purpose (INV-9, one process): a restart costs at most one
# extra fetch, which isn't worth a column and a migration.
_fitness_checked_on: Optional[date] = None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def poll_interval_min() -> int:
    """Poll interval in minutes (COROS_POLL_INTERVAL_MIN, default 15); 0 disables
    the scheduled job (manual sync still works)."""
    return max(0, _env_int("COROS_POLL_INTERVAL_MIN", DEFAULT_INTERVAL_MIN))


def lookback_days() -> int:
    return max(1, _env_int("COROS_POLL_LOOKBACK_DAYS", DEFAULT_LOOKBACK_DAYS))


@dataclass
class TickResult:
    """Outcome of one tick. `skipped` is set when nothing was attempted."""
    skipped: Optional[str] = None            # "not_connected" | "already_running"
    found: int = 0                           # runs COROS listed in the window
    queued: int = 0                          # new rows inserted as pending
    fitness_recorded: bool = False           # a changed fitness snapshot was saved
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.skipped is None and not self.errors


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _state(db: Session) -> CorosSyncState:
    st = db.get(CorosSyncState, _STATE_ID)
    if st is None:
        st = CorosSyncState(id=_STATE_ID, runs_found=0)
        db.add(st)
        db.flush()
    return st


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes for timezone=True columns; they were stored as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _window(db: Session, today: date) -> tuple[date, date]:
    last = _as_utc(_state(db).last_success_at)
    if last is None:
        days = FIRST_SYNC_LOOKBACK_DAYS
    else:
        gap = (today - last.astimezone(_TZ).date()).days + 1
        days = min(MAX_LOOKBACK_DAYS, max(lookback_days(), gap))
    return today - timedelta(days=days), today


def _to_pending(run: CorosRun) -> PendingCorosRun:
    return PendingCorosRun(
        label_id=run.label_id, sport_type=run.sport_type, run_date=run.run_date,
        distance_km=run.distance_km, moving_time_s=run.moving_time_s,
        elapsed_time_s=run.elapsed_time_s, avg_pace_s_per_km=run.avg_pace_s_per_km,
        avg_hr=run.avg_hr, calories=run.calories, elevation_gain_m=run.elevation_gain_m,
        avg_cadence=run.avg_cadence, training_load=run.training_load,
        training_focus=run.training_focus, start_timestamp=run.start_timestamp,
        end_timestamp=run.end_timestamp, status="pending",
        # Rounded at storage (R5.4.1): the inbox never holds full-precision coordinates.
        location_label=run.location_label,
        start_lat=round_coord(run.start_lat), start_lng=round_coord(run.start_lng),
    )


def run_tick(
    db: Session,
    *,
    trigger: str = "scheduled",
    client: Optional[CorosMcpClient] = None,
    today: Optional[date] = None,
) -> TickResult:
    """
    Run one poll. Never raises. Commits its own writes (pending rows + sync
    state); the caller supplies the session and owns closing it.

    `client` / `today` are test seams.
    """
    if not _tick_lock.acquire(blocking=False):
        return TickResult(skipped="already_running")
    try:
        status = conn.get_status(db)["status"]
        if status != conn.STATUS_CONNECTED:
            return TickResult(skipped="not_connected")
        return _tick(db, trigger, client, today or datetime.now(_TZ).date())
    finally:
        _tick_lock.release()


def _tick(db: Session, trigger: str, client: Optional[CorosMcpClient], today: date) -> TickResult:
    result = TickResult()
    st = _state(db)
    st.last_attempt_at = _utcnow()
    st.last_trigger = trigger
    db.commit()

    client = client or CorosMcpClient(lambda: conn.get_access_token(db))
    start, end = _window(db, today)
    try:
        runs = client.list_runs(start, end)
        result.found = len(runs)
        for run in runs:
            try:
                if _handle_run(db, client, run):
                    result.queued += 1
            except conn.CorosAuthError:
                raise
            except (CorosContractError, CorosApiError) as exc:
                db.rollback()
                logger.error("COROS run %s skipped: %s", run.label_id, exc)
                result.errors.append(f"run {run.label_id}: {exc}")
    except conn.CorosAuthError as exc:
        db.rollback()
        conn.mark_reauth_required(db, str(exc))
        result.errors.append("reconnect needed: COROS rejected our credentials")
    except requests.RequestException as exc:
        db.rollback()
        logger.warning("COROS poll failed (network): %s", type(exc).__name__)
        result.errors.append(f"COROS unreachable ({type(exc).__name__})")
    except (CorosContractError, CorosApiError) as exc:
        db.rollback()
        logger.error("COROS poll failed: %s", exc)
        result.errors.append(str(exc))
    except conn.CorosNotConfigured as exc:
        db.rollback()
        result.errors.append(f"not configured: {exc}")

    if not result.errors:
        if trigger == "manual" or result.queued or _fitness_checked_on != today:
            result.fitness_recorded = _sync_fitness(db, client, today)
        _scan_best_efforts(db, client)

    st = _state(db)
    st.runs_found = result.queued
    st.last_error = "; ".join(result.errors)[:1000] if result.errors else None
    if not result.errors:
        st.last_success_at = _utcnow()
    db.commit()
    logger.info("COROS poll (%s): listed=%d queued=%d errors=%d", trigger, result.found, result.queued, len(result.errors))
    return result


def _sync_fitness(db: Session, client: CorosMcpClient, today: date) -> bool:
    """R8.4.1: read COROS's fitness overview and save it when it changed.

    Called after a clean poll when the tick found a new run (COROS recomputes
    fitness after it processes a run), on a manual sync, or on the first tick of
    a Toronto day — not every 15 minutes. No confirmation (design decisions C13):
    a snapshot is a reading COROS computed, not a run. Like the best-effort scan,
    a failure is logged and never fails the poll; the day still counts as
    checked, so a broken parser logs once a day, not once a tick.
    Returns True when a snapshot was saved.
    """
    global _fitness_checked_on
    _fitness_checked_on = today
    try:
        fit = client.fitness_overview()
        snap = fitness_svc.record_if_changed(
            db, vo2max=fit.vo2max, running_level=fit.running_level,
            threshold_pace_s_per_km=fit.threshold_pace_s_per_km,
            race_predictions=fit.race_predictions,
        )
    except conn.CorosAuthError as exc:
        db.rollback()
        conn.mark_reauth_required(db, str(exc))
        return False
    except Exception as exc:  # never let fitness break the poll
        db.rollback()
        logger.warning("COROS fitness snapshot skipped: %s: %s", type(exc).__name__, exc)
        return False
    if snap is not None:
        logger.info("COROS fitness changed: snapshot %d saved", snap.id)
    return snap is not None


def _scan_best_efforts(db: Session, client: CorosMcpClient) -> None:
    """R8.2: fetch FIT files for a few confirmed COROS runs and store their best
    efforts. Best-effort in both senses — a failure here is logged and never
    marks the poll failed (the inbox is what the tick is for)."""
    try:
        summary = best_efforts_svc.scan_coros(db, client)
        if summary.scanned or summary.failed:
            logger.info("COROS best efforts: scanned=%d failed=%d", summary.scanned, summary.failed)
    except conn.CorosAuthError as exc:
        db.rollback()
        conn.mark_reauth_required(db, str(exc))
    except Exception as exc:  # never let derived data break the poll
        db.rollback()
        logger.warning("COROS best-effort scan skipped: %s", type(exc).__name__)


def _handle_run(db: Session, client: CorosMcpClient, run: CorosRun) -> bool:
    """Queue one run if new. Returns True when a row was inserted."""
    if db.query(PendingCorosRun.id).filter(PendingCorosRun.label_id == run.label_id).first():
        return False
    if coros_svc.is_already_logged(db, run.label_id, run.run_date.isoformat(), run.distance_km):
        return False
    full = client.fetch_run(run)
    row = _to_pending(full)
    sug = suggest_shoe(db, distance_km=full.distance_km, avg_pace_s_per_km=full.avg_pace_s_per_km)
    row.suggested_shoe_id, row.suggestion_reason = sug.shoe_id, sug.reason
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # lost a race on the UNIQUE label_id: someone queued it first — fine
        return False
    return True


def run_scheduled_tick() -> TickResult:
    """Scheduler entry (called via asyncio.to_thread): owns a fresh session."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        return run_tick(db, trigger="scheduled")
    finally:
        db.close()


def get_sync_summary(db: Session) -> dict:
    """Last-sync summary + queue depth for the UI / MCP status tool (no secrets)."""
    st = db.get(CorosSyncState, _STATE_ID)
    return {
        "last_attempt_at": _as_utc(st.last_attempt_at).isoformat() if st and st.last_attempt_at else None,
        "last_success_at": _as_utc(st.last_success_at).isoformat() if st and st.last_success_at else None,
        "last_trigger": st.last_trigger if st else None,
        "runs_found": st.runs_found if st else 0,
        "last_error": st.last_error if st else None,
        "pending_count": db.query(PendingCorosRun).filter(PendingCorosRun.status == "pending").count(),
        "poll_interval_min": poll_interval_min(),
    }
