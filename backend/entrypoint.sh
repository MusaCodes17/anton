#!/bin/bash
# Anton container entrypoint — Litestream restore-on-start + continuous replication.
#
# RA1.4: if LITESTREAM_BUCKET is set, this script:
#   1. Restores from the replica if /data/shoe_deals.db is absent (first deploy
#      or disaster recovery) — idempotent: skips restore if DB already exists.
#   2. Starts Litestream as the foreground process with uvicorn as its child;
#      Litestream forwards signals so the container exits cleanly when uvicorn does.
#
# Without LITESTREAM_BUCKET: runs uvicorn directly (dev / no-backup mode).
# INV-9: --workers 1 is an invariant (D4 scrape lock + E8 rate limiter are
# in-process; multiple workers silently break both). See CLAUDE.md §14.
set -euo pipefail

LITESTREAM_CONFIG=/app/litestream.yml
UVICORN_CMD="uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"

if [ -n "${LITESTREAM_BUCKET:-}" ]; then
    if [ ! -f /data/shoe_deals.db ]; then
        echo "No database found — attempting restore from Litestream replica..."
        if litestream restore -config "$LITESTREAM_CONFIG" -if-replica-exists /data/shoe_deals.db; then
            echo "Restore complete."
        else
            echo "No replica snapshot found; alembic will create a fresh database."
        fi
    else
        echo "Database already present — skipping restore."
    fi

    exec litestream replicate -config "$LITESTREAM_CONFIG" -exec "$UVICORN_CMD"
else
    echo "LITESTREAM_BUCKET not set — starting without replication."
    exec $UVICORN_CMD
fi
