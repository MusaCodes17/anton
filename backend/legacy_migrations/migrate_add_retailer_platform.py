"""
Migration: add a `platform` column to retailers.

Existing retailers get platform="custom" — this does NOT touch scraping_enabled
or remove any of their hardcoded scrapers, so they keep working exactly as
before. New retailers created via the API get auto-detected as "shopify",
"algolia", or "custom" (see app/scrapers/platform_detection.py).

Safe to run repeatedly — checks whether the column exists first. Usage (from
backend/):
    python migrate_add_retailer_platform.py
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
        print(f"No database at {path}; nothing to migrate (fresh DB gets the column from the model).")
        return

    conn = sqlite3.connect(path)
    try:
        existing = [row[1] for row in conn.execute("PRAGMA table_info(retailers)")]
        if "platform" in existing:
            print("✅ retailers.platform already present — skipping.")
            return
        conn.execute("ALTER TABLE retailers ADD COLUMN platform VARCHAR(20) NOT NULL DEFAULT 'custom'")
        conn.commit()
        print("✅ Added retailers.platform (default 'custom' for all existing rows).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
