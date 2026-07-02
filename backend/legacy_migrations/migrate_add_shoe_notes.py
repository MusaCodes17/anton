"""
Migration: add purchase_price to owned_shoes, create the shoe_notes table,
migrate any existing owned_shoes.notes text into a shoe_notes entry, then
drop the old notes column.

Safe to run repeatedly — every step checks current state first. Usage
(from backend/):
    python migrate_add_shoe_notes.py
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
        cols = [row[1] for row in conn.execute("PRAGMA table_info(owned_shoes)")]

        if "purchase_price" not in cols:
            conn.execute("ALTER TABLE owned_shoes ADD COLUMN purchase_price REAL")
            print("✅ Added owned_shoes.purchase_price.")
        else:
            print("✅ owned_shoes.purchase_price already present — skipping.")

        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        if "shoe_notes" not in tables:
            conn.execute(
                """
                CREATE TABLE shoe_notes (
                    id INTEGER PRIMARY KEY,
                    owned_shoe_id INTEGER NOT NULL REFERENCES owned_shoes(id),
                    body TEXT NOT NULL,
                    mileage_at_note REAL NOT NULL,
                    triggered_by VARCHAR(20) NOT NULL DEFAULT 'manual',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX ix_shoe_notes_owned_shoe_id ON shoe_notes (owned_shoe_id)")
            print("✅ Created shoe_notes table.")
        else:
            print("✅ shoe_notes table already exists — skipping.")

        cols = [row[1] for row in conn.execute("PRAGMA table_info(owned_shoes)")]
        if "notes" in cols:
            migrated = 0
            for shoe_id, notes, mileage in conn.execute(
                "SELECT id, notes, current_mileage FROM owned_shoes WHERE notes IS NOT NULL AND TRIM(notes) != ''"
            ):
                conn.execute(
                    "INSERT INTO shoe_notes (owned_shoe_id, body, mileage_at_note, triggered_by) "
                    "VALUES (?, ?, ?, 'manual')",
                    (shoe_id, notes, mileage),
                )
                migrated += 1
            conn.execute("ALTER TABLE owned_shoes DROP COLUMN notes")
            conn.commit()
            print(f"✅ Migrated {migrated} existing note(s) into shoe_notes and dropped owned_shoes.notes.")
        else:
            print("✅ owned_shoes.notes already absent — skipping.")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
