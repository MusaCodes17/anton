"""
One-shot Strava activities.csv importer.

Usage:
    python -m app.scripts.import_strava --csv ~/workspace/export_33354574/activities.csv

Idempotent: re-running after a fresh export updates existing rows in place
(keyed on Strava's Activity ID), never duplicating.
"""
import argparse
import os
import sys

from app.database import SessionLocal
from app.services import strava_import


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a Strava bulk export activities.csv")
    parser.add_argument("--csv", required=True, help="Path to activities.csv from the Strava export")
    args = parser.parse_args()

    csv_path = os.path.expanduser(args.csv)
    if not os.path.isfile(csv_path):
        print(f"error: CSV not found at {csv_path}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        stats = strava_import.import_from_csv(csv_path, db)
    finally:
        db.close()

    print("Strava import complete:")
    print(f"  total activities: {stats.total}")
    print(f"  inserted:         {stats.inserted}")
    print(f"  updated:          {stats.updated}")
    print(f"  runs:             {stats.runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
