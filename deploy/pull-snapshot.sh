#!/bin/bash
# Pull the latest Litestream replica snapshot to ~/anton-data-mirror/ — RA1.4.
#
# Run periodically on the laptop to keep a local copy of the production DB.
# The mirror serves as the dev-DB seed: set DATABASE_URL to the mirror path
# for local development sessions (so the laptop never writes to production).
#
# Prerequisites:
#   - litestream installed locally (https://litestream.io/install/)
#   - LITESTREAM_* env vars exported (same values as the production .env)
#
# Usage:
#   export LITESTREAM_BUCKET=... LITESTREAM_ENDPOINT=... etc.
#   ./pull-snapshot.sh
#
# Output: ~/anton-data-mirror/shoe_deals.db

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LITESTREAM_CONFIG="${SCRIPT_DIR}/../backend/litestream.yml"
MIRROR_DIR="${HOME}/anton-data-mirror"
RESTORE_PATH="${MIRROR_DIR}/shoe_deals.db"
PREV_PATH="${RESTORE_PATH}.prev"

if [ -z "${LITESTREAM_BUCKET:-}" ]; then
    echo "Error: LITESTREAM_BUCKET is not set." >&2
    echo "  export LITESTREAM_BUCKET=... LITESTREAM_ENDPOINT=... etc." >&2
    exit 1
fi

mkdir -p "$MIRROR_DIR"

# Rename the existing mirror so Litestream can write a fresh restore.
# Kept until the new restore succeeds; removed on success.
if [ -f "$RESTORE_PATH" ]; then
    mv "$RESTORE_PATH" "$PREV_PATH"
    echo "Moved previous snapshot to $(basename "$PREV_PATH")"
fi

echo "Pulling latest snapshot from replica..."
if litestream restore -config "$LITESTREAM_CONFIG" -if-replica-exists "$RESTORE_PATH"; then
    if [ -f "$RESTORE_PATH" ]; then
        COUNT="$(sqlite3 "$RESTORE_PATH" 'SELECT COUNT(*) FROM activities;')"
        echo "Snapshot pulled: $RESTORE_PATH ($COUNT activities)"
        rm -f "$PREV_PATH"
    else
        echo "No replica found yet (replication may not have started). Restoring previous copy."
        mv -f "$PREV_PATH" "$RESTORE_PATH" 2>/dev/null || true
    fi
else
    echo "Restore failed. Restoring previous copy." >&2
    mv -f "$PREV_PATH" "$RESTORE_PATH" 2>/dev/null || true
    exit 1
fi
