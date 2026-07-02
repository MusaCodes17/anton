"""
Migration: add msrp column to shoes.

Separates "manufacturer's list price" from target_price ("price we want to
pay") — previously target_price did double duty as a stand-in for the
original/retail price in several UI spots, which is misleading whenever the
target is set below MSRP. Nullable, so existing rows stay valid; backfill it
manually per shoe via the edit form.

Safe to run repeatedly — it checks whether the column exists first. Usage
(from backend/):
    python migrate_add_msrp.py
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
        existing = [row[1] for row in conn.execute("PRAGMA table_info(shoes)")]
        if "msrp" in existing:
            print("✅ shoes.msrp already present — skipping.")
        else:
            conn.execute("ALTER TABLE shoes ADD COLUMN msrp FLOAT")
            print("✅ Added shoes.msrp (FLOAT).")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
