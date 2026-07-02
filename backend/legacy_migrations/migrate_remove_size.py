"""
One-off migration: drop the now-removed `size` column from the shoes table.

Safe to run multiple times — it checks whether the column exists first.
Usage (from backend/):  python migrate_remove_size.py
"""
import os
import sqlite3
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _db_path() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./shoe_deals.db")
    if not url.startswith("sqlite"):
        raise SystemExit(f"This migration only supports SQLite, got: {url}")
    # sqlite:///./shoe_deals.db -> ./shoe_deals.db
    return url.split("sqlite:///", 1)[-1]


def main():
    path = _db_path()
    if not os.path.exists(path):
        print(f"No database at {path}; nothing to migrate (a fresh DB won't have the column).")
        return

    conn = sqlite3.connect(path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(shoes)")]
        if "size" not in cols:
            print("✅ 'size' column already absent — nothing to do.")
            return

        conn.execute("ALTER TABLE shoes DROP COLUMN size")
        conn.commit()
        print("✅ Dropped 'size' column from shoes table.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
