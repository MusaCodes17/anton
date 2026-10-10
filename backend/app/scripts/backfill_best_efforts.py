"""
Backfill best efforts for the Strava archive (R8.2).

Scans every archived Strava run's FIT/GPX file from the bulk export folder and
stores its segment best efforts and its start location (R5.4.1: the first GPS
fix, rounded to ~100 m) in one walk (services/best_efforts.scan_archive). Run it
where both the export and the database are reachable — e.g. copy the export's
`activities/` folder to the server, or run locally against a DB copy.
Idempotent: runs already scanned are skipped. Runs scanned before R5.4.1 have no
location yet, so run once with --rescan to fill it (this also rebuilds their best
efforts, which is idempotent: each scan replaces the run's rows). Runs without
GPS data stay without a location; that is not a failure.
COROS runs are not covered here; the poll tick scans those (and gets their
location from the run list).

    python -m app.scripts.backfill_best_efforts --export-dir ~/Workspace/export_33354574

Exit codes: 0 ok, 1 some runs failed (see the summary), 2 bad arguments.
"""
import argparse
import sys
from pathlib import Path

from app.database import SessionLocal
from app.services import best_efforts as best_efforts_svc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--export-dir", required=True, type=Path,
                   help="Strava bulk export folder (the one containing activities/)")
    p.add_argument("--rescan", action="store_true", help="re-scan runs that were already scanned (also fills start location for runs scanned before R5.4.1)")
    args = p.parse_args(argv)

    export_dir = args.export_dir.expanduser()
    if not (export_dir / "activities").is_dir():
        print(f"error: {export_dir}/activities not found", file=sys.stderr)
        return 2

    def progress(i, n):
        if i % 50 == 0 or i == n:
            print(f"  {i}/{n}", flush=True)

    db = SessionLocal()
    try:
        s = best_efforts_svc.scan_archive(db, export_dir, rescan=args.rescan, progress=progress)
    finally:
        db.close()
    print(f"scanned {s.scanned} · no stream {s.no_stream} · failed {s.failed} · {s.efforts} efforts stored")
    for e in s.errors[:20]:
        print(f"  failed: {e}")
    return 1 if s.failed else 0


if __name__ == "__main__":
    sys.exit(main())
