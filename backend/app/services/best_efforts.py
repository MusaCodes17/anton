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

Per-km splits (R5.4.3, R11.6) are written alongside the efforts in the same scan
(`activity_splits`, with per-km average heart rate and elevation gain/loss read from the same file) under the same derived-data rules: a scan replaces the run's
split rows, and they die with the activity. Each scan records the engine version
that produced it (SCAN_VERSION); settled `ok` scans below it are re-scanned once
by the plain (non-rescan) path, which is how runs scanned before splits existed
gain them. Version-upgrade rescans re-download COROS FITs at the same ration
(COROS_SCANS_PER_TICK per tick), newest first; archive runs need the backfill
run once against the export.

Location (R5.4.1): an archive scan also reads the run's first GPS fix and
writes it to the activity row as `start_lat`/`start_lng`, rounded to ~100 m
(utils/location.round_coord). That makes the scan write exactly two columns on
the activity row. It never writes distance, time, attribution or mileage
(INV-1/INV-2 unchanged). COROS runs get their location from the run list, so
`scan_coros` does not pass a start point.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests
from sqlalchemy.orm import Session

from app.models.models import (
    Activity, ActivityBestEffort, ActivityEffortScan, ActivitySplit, PendingCorosRun,
)
from app.utils import best_efforts as engine
from app.utils.location import round_coord

logger = logging.getLogger(__name__)

MAX_SCAN_ATTEMPTS = 3        # a failed download/parse is retried on later ticks, then left alone
COROS_SCANS_PER_TICK = 5     # rations the daily COROS FIT download limit (size unknown)
FIT_DOWNLOAD_TIMEOUT_S = 30
SCAN_VERSION = 2             # bump when a scan starts producing new data; settled ok scans below it are re-scanned once (R5.4.3 added splits)


@dataclass
class ScanSummary:
    scanned: int = 0          # runs whose stream was read (status ok)
    no_stream: int = 0        # file had no usable distance stream
    failed: int = 0
    efforts: int = 0          # effort rows written
    splits: int = 0           # per-km split rows written
    errors: list[str] = field(default_factory=list)


def store_scan(db: Session, activity_id: int, stream: engine.Stream, *, source: str,
               start: Optional[tuple[float, float]] = None,
               hr: Optional[list] = None, alt: Optional[list] = None) -> int:
    """Replace one run's best efforts and per-km splits from its stream and
    record the scan. When `start` (lat, lon in degrees) is given, also stamp the
    activity's start point, rounded to ~100 m; that is the only activity column
    touched. `hr`/`alt` are the stream-aligned heart-rate and altitude channels
    (engine.fit_records / gpx_records) used for the splits. Returns the number of
    effort rows written (see `store_scan_counts` for the split count too). Caller
    owns the commit."""
    return store_scan_counts(db, activity_id, stream, source=source, start=start, hr=hr, alt=alt)[0]


def store_scan_counts(db: Session, activity_id: int, stream: engine.Stream, *, source: str,
                      start: Optional[tuple[float, float]] = None,
                      hr: Optional[list] = None, alt: Optional[list] = None) -> tuple[int, int]:
    """`store_scan`, returning (effort rows, split rows) written. Caller owns the commit."""
    db.query(ActivityBestEffort).filter(ActivityBestEffort.activity_id == activity_id).delete()
    db.query(ActivitySplit).filter(ActivitySplit.activity_id == activity_id).delete()
    efforts = engine.best_efforts(stream, source=source) if stream else {}
    for label, (elapsed_s, start_m) in efforts.items():
        db.add(ActivityBestEffort(
            activity_id=activity_id, distance_label=label,
            elapsed_s=elapsed_s, start_offset_m=start_m, source=source,
        ))
    splits = engine.km_splits(stream, source=source, hr=hr, alt=alt) if stream else []
    for sp in splits:
        db.add(ActivitySplit(
            activity_id=activity_id, split_index=sp.index, distance_m=sp.distance_m,
            elapsed_s=sp.elapsed_s, moving_s=sp.moving_s, source=source,
            avg_hr=sp.avg_hr, elev_gain_m=sp.elev_gain_m, elev_loss_m=sp.elev_loss_m,
        ))
    if start is not None:
        activity = db.get(Activity, activity_id)
        activity.start_lat = round_coord(start[0])
        activity.start_lng = round_coord(start[1])
    _mark_scan(db, activity_id, status="ok" if stream else "no_stream", source=source)
    return len(efforts), len(splits)


def _mark_scan(db: Session, activity_id: int, *, status: str, source: Optional[str] = None,
               error: Optional[str] = None) -> None:
    """Record a scan outcome. `attempts` counts tries for the row's current
    scan_version: a settled scan (ok/no_stream) resets it to 1 at SCAN_VERSION.
    A failure on a new or already-failed row marks it failed and counts a try.
    A failure while *upgrading* an `ok` row (e.g. a transient COROS error) keeps
    the row `ok` at its old scan_version, because the rollback left its efforts
    and splits untouched, and readers (strava_stats.best_efforts_among) treat only
    `ok` as scanned; it records the error and counts a try, so the upgrade is
    retried up to MAX_SCAN_ATTEMPTS and then left alone."""
    scan = db.get(ActivityEffortScan, activity_id)
    if status != "failed":
        if scan is None:
            db.add(ActivityEffortScan(activity_id=activity_id, status=status, source=source,
                                      attempts=1, error=error, scan_version=SCAN_VERSION))
        else:
            scan.status, scan.source, scan.error = status, source, error
            scan.attempts, scan.scan_version = 1, SCAN_VERSION
    elif scan is None:
        db.add(ActivityEffortScan(activity_id=activity_id, status="failed", source=source,
                                  attempts=1, error=error))
    elif scan.status == "ok":
        scan.error = error                      # status, source, version stay: the data is still good
        scan.attempts = (scan.attempts or 0) + 1
    else:
        scan.status, scan.source, scan.error = "failed", source, error
        scan.attempts = (scan.attempts or 0) + 1


def _needs_scan(db: Session, *, rescan: bool):
    """Run activities with no settled scan (ok/no_stream), with retries left, or
    whose `ok` scan predates SCAN_VERSION (a one-time upgrade rescan). The attempts
    limit applies to failed rows and to upgrade rescans (`attempts` counts tries for
    the current scan_version, so settled scans start at 1); `no_stream` is never re-picked for upgrade
    (the file had nothing to derive from, and a newer engine reads the same stream)."""
    q = db.query(Activity).filter(Activity.activity_type == "Run")
    if rescan:
        return q
    return q.outerjoin(ActivityEffortScan, ActivityEffortScan.activity_id == Activity.id).filter(
        (ActivityEffortScan.activity_id.is_(None))
        | ((ActivityEffortScan.status == "failed") & (ActivityEffortScan.attempts < MAX_SCAN_ATTEMPTS))
        | ((ActivityEffortScan.status == "ok") & (ActivityEffortScan.scan_version < SCAN_VERSION)
           & (ActivityEffortScan.attempts < MAX_SCAN_ATTEMPTS))
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
            # Read the file once; the stream parser and the start-point reader share it.
            if source == "fit":
                raw = path.read_bytes()
                stream, hr, alt = engine.fit_records(raw)
                start = engine.fit_start(raw)
            else:
                text = path.read_bytes().decode("utf-8", "replace")
                stream, hr, alt = engine.gpx_records(text)
                start = engine.gpx_start(text)
            n, m = store_scan_counts(db, a.id, stream, source=source, start=start, hr=hr, alt=alt)
            out.efforts += n
            out.splits += m
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
    """Scan up to `limit` logged COROS runs that have no settled scan (or an `ok`
    scan from an older SCAN_VERSION), newest
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
            stream, hr, alt = engine.fit_records(resp.content)
            n, m = store_scan_counts(db, a.id, stream, source="fit", hr=hr, alt=alt)
            out.efforts += n
            out.splits += m
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
