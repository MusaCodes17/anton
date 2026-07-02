"""
Migration: add coros_activity_id to shoe_runs, create app_settings table.

Safe to run repeatedly — every step checks current state first. Usage
(from backend/):
    python migrate_add_coros.py
"""
import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()


def _db_path() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./shoe_deals.db")
    if not url.startswith("sqlite"):
        raise SystemExit(f"This migration only supports SQLite, got: {url}")
    return url.split("sqlite:///", 1)[-1]


def main():
    path = _db_path()
    if not os.path.exists(path):
        print(f"No database at {path}; nothing to migrate (fresh DB gets the new schema directly).")
        return

    conn = sqlite3.connect(path)
    try:
        run_cols = [row[1] for row in conn.execute("PRAGMA table_info(shoe_runs)")]
        if "coros_activity_id" not in run_cols:
            conn.execute("ALTER TABLE shoe_runs ADD COLUMN coros_activity_id TEXT")
            print("✅ Added shoe_runs.coros_activity_id.")
        else:
            print("✅ shoe_runs.coros_activity_id already present — skipping.")

        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        if "app_settings" not in tables:
            conn.execute(
                """
                CREATE TABLE app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            print("✅ Created app_settings table.")
        else:
            print("✅ app_settings table already exists — skipping.")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
