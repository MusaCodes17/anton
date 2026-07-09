#!/bin/bash
# Anton DB restore from Litestream replica — RA1.4.
#
# Use for the restore drill (required before RA1.5 cutover) or disaster
# recovery. Run this on the host machine (not inside the container).
#
# Prerequisites:
#   - litestream installed locally (https://litestream.io/install/)
#   - LITESTREAM_* env vars exported (same values as the production .env)
#
# RESTORE DRILL PROCEDURE (perform once before RA1.5 cutover):
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
