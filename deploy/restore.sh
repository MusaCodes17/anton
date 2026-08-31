#!/bin/bash
# Anton DB restore from Litestream replica — RA1.4.
#
# Use for the restore drill (required before RA1.5 cutover) or disaster
# recovery.
#
# PRIMARY METHOD — routine drill, run via `docker compose exec` (2026-08-29):
# `litestream` and `sqlite3` are only installed INSIDE the app image (see
# backend/Dockerfile) — the Hetzner host itself has neither, so this script
# fails on the host with "litestream: command not found" unless you install
# the binary there separately. There's no need to: the container already has
# everything, and the production litestream.yml config is already mounted at
# /app/litestream.yml inside it. Run the drill straight through the container:
#
#   cd ~/anton
#   docker compose exec anton litestream restore \
#     -config /app/litestream.yml \
#     -o /tmp/drill-restore.db \
#     /data/shoe_deals.db
#
# NOTE the two different paths: `/data/shoe_deals.db` (the LAST positional
# arg) must be the database path exactly as DECLARED in litestream.yml's
# `dbs:` list — litestream uses it to look up which replica to restore FROM,
# it is not where output goes. `-o /tmp/drill-restore.db` is the actual
# output destination (a scratch path — never point -o at the live DB path).
# Passing an undeclared path as the positional arg fails with
# "database not found in config: <path>".
#
# Then verify counts the same way (sqlite3 is also container-only):
#   docker compose exec anton sqlite3 /tmp/drill-restore.db "SELECT COUNT(*) FROM activities;"
#   docker compose exec anton sqlite3 /tmp/drill-restore.db "SELECT COUNT(*) FROM shoe_runs;"
#   docker compose exec anton sqlite3 /tmp/drill-restore.db "PRAGMA integrity_check;"
# Compare against the live DB the same way (swap in /data/shoe_deals.db) —
# counts should match or be within a few seconds/minutes of lag (sync-interval
# is 1s + continuous replication; a large gap means something is actually wrong).
# Clean up after: docker compose exec anton rm /tmp/drill-restore.db
#
# ---
#
# THIS SCRIPT (below) — an alternative for running restore from a machine
# that has `litestream` installed natively (https://litestream.io/install/)
# and can reach B2 directly — e.g. a genuinely fresh recovery machine that
# never had the Anton container, which is the real disaster-recovery scenario
# this script exists for. Not the routine-drill path above; that path is the
# containerized one-liner, since a routine drill runs against the same host
# that's already running the container.
#
# Prerequisites for using this script directly:
#   - litestream installed locally (https://litestream.io/install/)
#   - LITESTREAM_* env vars exported (same values as the production .env)
#
# RESTORE DRILL PROCEDURE (perform once before RA1.5 cutover) — via this script:
#
#   1. Export credentials:
#        export LITESTREAM_BUCKET=your-bucket
#        export LITESTREAM_ENDPOINT=https://s3.region.backblazeb2.com
#        export LITESTREAM_ACCESS_KEY_ID=...
#        export LITESTREAM_SECRET_ACCESS_KEY=...
#
#   2. Run against a scratch path (do NOT overwrite the live DB):
#        RESTORE_PATH=/tmp/drill-restore.db ./restore.sh
#
#   3. Verify the restored database:
#        sqlite3 /tmp/drill-restore.db "SELECT COUNT(*) FROM activities;"
#        # Must match the live count (933+ activities as of 2026-07-09)
#        sqlite3 /tmp/drill-restore.db "SELECT COUNT(*) FROM shoe_runs;"
#
#   4. Record the drill result in docs/changelog.md before declaring RA1.4 done.
#
# Point-in-time restore to a specific timestamp:
#   RESTORE_TIMESTAMP=2026-07-09T18:00:00Z RESTORE_PATH=/tmp/pit.db ./restore.sh
#
# Disaster recovery — restore the live path (container must be stopped first):
#   RESTORE_PATH=/data/shoe_deals.db ./restore.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LITESTREAM_CONFIG="${SCRIPT_DIR}/../backend/litestream.yml"
RESTORE_PATH="${RESTORE_PATH:-/tmp/anton-restore-$(date +%Y%m%d%H%M%S).db}"

if [ -z "${LITESTREAM_BUCKET:-}" ]; then
    echo "Error: LITESTREAM_BUCKET is not set. Export your Litestream credentials first." >&2
    echo "  export LITESTREAM_BUCKET=... LITESTREAM_ENDPOINT=... etc." >&2
    exit 1
fi

if [ -f "$RESTORE_PATH" ]; then
    echo "Error: $RESTORE_PATH already exists. Move or remove it first, or set RESTORE_PATH to a new path." >&2
    exit 1
fi

RESTORE_ARGS=(-config "$LITESTREAM_CONFIG")
if [ -n "${RESTORE_TIMESTAMP:-}" ]; then
    RESTORE_ARGS+=(-timestamp "$RESTORE_TIMESTAMP")
    echo "Restoring to point-in-time: $RESTORE_TIMESTAMP"
fi
RESTORE_ARGS+=("$RESTORE_PATH")

echo "Restoring to: $RESTORE_PATH"
litestream restore "${RESTORE_ARGS[@]}"

echo ""
echo "Restore complete. Verify counts:"
echo "  sqlite3 '$RESTORE_PATH' \"SELECT COUNT(*) FROM activities;\""
echo "  sqlite3 '$RESTORE_PATH' \"SELECT COUNT(*) FROM shoe_runs;\""
