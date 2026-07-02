"""
Migration: add sizes_available column to price_records and deals.

Stores the list of available sizes returned by the scraper at record time
(e.g. ["8", "8.5", "9", "10"]) as JSON text — SQLite has no native array type,
and SQLAlchemy's JSON column type already (de)serializes Python lists through
it transparently. Nullable so existing rows stay valid (no backfill; older
records simply have no size data until the next scrape lazily populates it).

Safe to run repeatedly — it checks whether each column exists first. Usage
(from backend/):
    python migrate_add_sizes.py
"""
import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()

# (table, column, SQLite type)
COLUMNS = [
    ("price_records", "sizes_available", "JSON"),
    ("deals", "sizes_available", "JSON"),
]


def _db_path() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./shoe_deals.db")
    if not url.startswith("sqlite"):
        raise SystemExit(f"This migration only supports SQLite, got: {url}")
    return url.split("sqlite:///", 1)[-1]


def main():
    path = _db_path()
    if not os.path.exists(path):
        print(f"No database at {path}; nothing to migrate (fresh DB gets the columns from the model).")
        return

    conn = sqlite3.connect(path)
    try:
        for table, column, coltype in COLUMNS:
            existing = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
            if column in existing:
                print(f"✅ {table}.{column} already present — skipping.")
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            print(f"✅ Added {table}.{column} ({coltype}).")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
