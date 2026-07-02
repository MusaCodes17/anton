"""
Migration: add shoe_type column to shoes (tracked-shoe) table and run a
best-effort keyword migration on both shoes and owned_shoes.

Safe to re-run — column add is skipped when already present, and
keyword matching only updates rows where shoe_type IS NULL.

Usage (from backend/):
    python migrate_add_shoe_type.py
"""
import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()

# Ordered rules — first match wins, so more-specific prefixes must come first.
SHOE_TYPE_RULES = [
    ("long_distance_racer", ["adios pro", "alphafly", "metaspeed sky", "deviate nitro elite", "carbon x", "endorphin pro"]),
    ("short_distance_racer", ["adios 9", "dragonfly", "streakfly", "rocket", "vaporfly"]),
    ("long_run", ["long run", "longrun"]),
    ("tempo", ["boston", "endorphin speed", "neo zen", "deviate nitro", "zoom fly", "neo vista"]),
    ("intervals", ["adios", "track", "spike", "zoom 400"]),
    ("daily_trainer", ["pegasus", "gel-nimbus", "gel-kayano", "ghost", "evo sl", "clifton", "bondi", "novablast", "superblast"]),
    ("trail", ["trail", "speedgoat", "peregrine", "scout", "wildhorse"]),
    ("recovery", ["slide", "recovery", "oofos", "hoka ora"]),
]


def _db_path() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./shoe_deals.db")
    if not url.startswith("sqlite"):
        raise SystemExit(f"This migration only supports SQLite, got: {url}")
    return url.split("sqlite:///", 1)[-1]


def classify_shoe(model: str) -> str | None:
    """Return the first matching shoe_type for a model name, or None."""
    model_lower = model.lower()
    for shoe_type, keywords in SHOE_TYPE_RULES:
        for keyword in keywords:
            if keyword in model_lower:
                return shoe_type
    return None


def _migrate_table(conn: sqlite3.Connection, table: str) -> tuple[int, int]:
    """Classify NULL shoe_type rows in `table`. Returns (updated, still_null) counts."""
    rows = conn.execute(f"SELECT id, model FROM {table} WHERE shoe_type IS NULL").fetchall()
    updated = 0
    for row_id, model in rows:
        shoe_type = classify_shoe(model)
        if shoe_type:
            conn.execute(f"UPDATE {table} SET shoe_type = ? WHERE id = ?", (shoe_type, row_id))
            updated += 1
    total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    still_null = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE shoe_type IS NULL").fetchone()[0]
    return updated, still_null, total


def main():
    path = _db_path()
    if not os.path.exists(path):
        print(f"No database at {path}; nothing to migrate (fresh DB gets the column from the model).")
        return

    conn = sqlite3.connect(path)
    try:
        # Step 1: Add shoe_type to the tracked-shoes table (owned_shoes already has it).
        existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(shoes)")]
        if "shoe_type" not in existing_cols:
            conn.execute("ALTER TABLE shoes ADD COLUMN shoe_type VARCHAR(50)")
            print("✅ Added shoes.shoe_type column.")
        else:
            print("✅ shoes.shoe_type already present — skipping column add.")

        # Step 2: Keyword migration on both tables.
        updated_s, null_s, total_s = _migrate_table(conn, "shoes")
        updated_o, null_o, total_o = _migrate_table(conn, "owned_shoes")

        conn.commit()

        print(f"✅ shoes:       {updated_s} updated, {null_s}/{total_s} remain null.")
        print(f"✅ owned_shoes: {updated_o} updated, {null_o}/{total_o} remain null.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
