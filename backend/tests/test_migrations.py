"""T4 — exercise the Alembic path production actually boots on.

`database.run_migrations()` runs `alembic upgrade head` at startup (R2.2, the
sole schema authority), but the suite's `db` fixture builds schema with
`create_all` and never touches Alembic. A broken migration chain (a bad
`down_revision`, a batch-mode SQLite slip, a revision that doesn't apply on a
fresh DB) would therefore pass every other test and only surface on a real
deploy — exactly the RA1.5 cutover moment.

This test builds a fresh SQLite file and runs `alembic upgrade head` as a
subprocess — the production invocation verbatim — asserting it applies cleanly
and the load-bearing tables from across the chain exist. `DATABASE_URL` is
pointed at a tmp file; `load_dotenv(override=False)` in env.py means the
subprocess env wins, so the live DB is never touched.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# One representative table per era of the migration chain — if any is missing,
# a revision failed to apply on a fresh DB.
EXPECTED_TABLES = (
    "shoes", "retailers", "deals", "price_records", "promo_codes",
    "owned_shoes", "shoe_notes",
    "activities", "shoe_runs", "planned_races", "strava_gear_mappings",
    "athlete_metrics", "scrape_runs",
    "chat_conversations", "checkpoint_prompts",
    "oauth_auth_codes", "oauth_tokens",
    "sessions",
    "alembic_version",
)


def test_alembic_upgrade_head_on_fresh_db(tmp_path):
    db_path = tmp_path / "fresh.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stderr}"
    assert db_path.exists(), "migration did not create the database file"

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        head = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        conn.close()

    missing = [t for t in EXPECTED_TABLES if t not in tables]
    assert not missing, f"tables missing after upgrade head: {missing}"

    # Exactly one head revision was stamped.
    assert head is not None and head[0], "alembic_version was not stamped"
