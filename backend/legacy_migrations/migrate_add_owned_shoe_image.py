"""
Migration: add image_url column to owned_shoes.

Adds a nullable column so existing rows stay valid. Safe to run repeatedly —
it checks whether the column exists first. Usage (from backend/):
    python migrate_add_owned_shoe_image.py
"""
import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()

COLUMNS = [
    ("owned_shoes", "image_url", "TEXT"),
]


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
