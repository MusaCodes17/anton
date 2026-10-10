"""
Best efforts inside runs (R8.2) — scanning runs' per-second streams into
`activity_best_efforts`. The engine (stream parsing, sliding window) is pure
and lives in app/utils/best_efforts; this module owns where streams come from
and what gets stored. Decision: docs/design_decisions.md B19.

Two sources:
- **The Strava archive:** each `source='strava'` activity carries `fit_filename`
  (`activities/<id>.fit.gz` or `.gpx`) relative to the bulk export folder. The
  export lives wherever it was downloaded, so the archive scan is a one-off
  script run against that folder (scripts/backfill_best_efforts).
- **COROS runs:** the run's FIT file comes from the COROS MCP server by label id
  (`coros_activity_id`). Downloads count against a daily COROS limit, so the
  poll tick scans a few per tick (COROS_SCANS_PER_TICK) after a run is logged —
  never on the confirm path, which stays fast and network-free.

Efforts are derived data: a scan replaces the run's rows. Raw files are never
stored, and the COROS FIT URL (an unsigned S3 link) is never stored or logged.
None of this touches runs, attributions or mileage (INV-1/INV-2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests
from sqlalchemy.orm import Session

from app.models.models import Activity, ActivityBestEffort, ActivityEffortScan, PendingCorosRun
from app.utils import best_efforts as engine

logger = logging.getLogger(__name__)

MAX_SCAN_ATTEMPTS = 3        # a failed download/parse is retried on later ticks, then left alone
COROS_SCANS_PER_TICK = 5     # rations the daily COROS FIT download limit (size unknown)
FIT_DOWNLOAD_TIMEOUT_S = 30


@dataclass
class ScanSummary:
    scanned: int = 0          # runs whose stream was read (status ok)
    no_stream: int = 0        # file had no usable distance stream
    failed: int = 0
    efforts: int = 0          # effort rows written
    errors: list[str] = field(default_factory=list)


def store_scan(db: Session, activity_id: int, stream: engine.Stream, *, source: str) -> int:
    """Replace one run's best efforts from its stream and record the scan.
    Returns the number of effort rows written. Caller owns the commit."""
    db.query(ActivityBestEffort).filter(ActivityBestEffort.activity_id == activity_id).delete()
    efforts = engine.best_efforts(stream, source=source) if stream else {}
    for label, (elapsed_s, start_m) in efforts.items():
        db.add(ActivityBestEffort(
            activity_id=activity_id, distance_label=label,
            elapsed_s=elapsed_s, start_offset_m=start_m, source=source,
        ))
    _mark_scan(db, activity_id, status="ok" if stream else "no_stream", source=source)
    return len(efforts)


def _mark_scan(db: Session, activity_id: int, *, status: str, source: Optional[str] = None,
               error: Optional[str] = None) -> None:
    scan = db.get(ActivityEffortScan, activity_id)
    if scan is None:
        db.add(ActivityEffortScan(activity_id=activity_id, status=status, source=source,
                                  attempts=1, error=error))
    else:
        scan.status, scan.source, scan.error = status, source, error
        scan.attempts = (scan.attempts or 0) + 1


def _needs_scan(db: Session, *, rescan: bool):
    """Run activities with no settled scan (ok/no_stream), or with retries left."""
    q = db.query(Activity).filter(Activity.activity_type == "Run")
    if rescan:
        return q
    return q.outerjoin(ActivityEffortScan, ActivityEffortScan.activity_id == Activity.id).filter(
        (ActivityEffortScan.activity_id.is_(None))
        | ((ActivityEffortScan.status == "failed") & (ActivityEffortScan.attempts < MAX_SCAN_ATTEMPTS))
    )


def scan_archive(db: Session, export_dir: Path, *, rescan: bool = False,
                 progress: Optional[Callable[[int, int], None]] = None) -> ScanSummary:
    """Scan every archived Strava run against the bulk export folder. Idempotent:
    settled runs are skipped unless `rescan`. Commits per run, so an interrupted
    backfill keeps what it did. One run's bad file never stops the rest."""
    export_dir = Path(export_dir)
    todo = (
        _needs_scan(db, rescan=rescan)
        .filter(Activity.source == "strava", Activity.fit_filename.isnot(None))
        .order_by(Activity.id)
        .all()
    )
    out = ScanSummary()
    for i, a in enumerate(todo, 1):
        path = export_dir / a.fit_filename
        source = "gpx" if a.fit_filename.endswith(".gpx") else "fit"
        try:
            if source == "fit":
                stream = engine.fit_stream(path.read_bytes())
            else:
                with path.open("rb") as fh:
                    stream = engine.gpx_stream(fh)
            n = store_scan(db, a.id, stream, source=source)
            out.efforts += n
            if stream:
                out.scanned += 1
            else:
                out.no_stream += 1
        except Exception as exc:  # isolate: a missing/corrupt file is one run's problem
            db.rollback()
            _mark_scan(db, a.id, status="failed", error=f"{type(exc).__name__}: {exc}"[:300])
            out.failed += 1
            out.errors.append(f"activity {a.id} ({a.fit_filename}): {type(exc).__name__}")
            logger.warning("Best efforts: activity %s (%s) failed: %s", a.id, a.fit_filename, exc)
        db.commit()
        if progress:
            progress(i, len(todo))
    return out


def scan_coros(db: Session, client, *, limit: int = COROS_SCANS_PER_TICK,
               get: Callable[..., requests.Response] = requests.get) -> ScanSummary:
    """Scan up to `limit` logged COROS runs that have no settled scan, newest
    first: ask COROS for the FIT URL, download it, parse in memory, store the
    efforts. Called from the poll tick after polling (one thread, INV-9).
    Auth errors propagate (the tick handles reconnect state); anything else is
    recorded per run and retried on a later tick, up to MAX_SCAN_ATTEMPTS."""
    from app.services import coros_connection as conn

    todo = (
        _needs_scan(db, rescan=False)
        .filter(Activity.coros_activity_id.isnot(None))
        .order_by(Activity.run_date.desc(), Activity.id.desc())
        .limit(limit)
        .all()
    )
    out = ScanSummary()
    for a in todo:
        label_id = a.coros_activity_id
        sport_type = (
            db.query(PendingCorosRun.sport_type).filter(PendingCorosRun.label_id == label_id).scalar()
            or 100
        )
        try:
            url = client.fit_url(label_id, sport_type)
            resp = get(url, timeout=FIT_DOWNLOAD_TIMEOUT_S)
            resp.raise_for_status()
            stream = engine.fit_stream(resp.content)
            n = store_scan(db, a.id, stream, source="fit")
            out.efforts += n
            if stream:
                out.scanned += 1
            else:
                out.no_stream += 1
        except conn.CorosAuthError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            # The exception text can carry the FIT URL (requests errors do) — keep only the type.
            _mark_scan(db, a.id, status="failed", source="fit", error=type(exc).__name__)
            out.failed += 1
            out.errors.append(f"activity {a.id}: {type(exc).__name__}")
            logger.warning("Best efforts: COROS run %s (activity %s) failed: %s", label_id, a.id, type(exc).__name__)
        db.commit()
    return out
