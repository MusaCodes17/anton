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
#
# RA1.6: --proxy-headers + --forwarded-allow-ips="*" make uvicorn trust Caddy's
# X-Forwarded-Proto: https (deploy/Caddyfile already sends it). Without this,
# Starlette builds the /mcp trailing-slash 307 from uvicorn's own (http) view of
# the request and downgrades the redirect to http://, which OAuth-aware clients
# (the claude.ai connector) refuse to follow — "Authorization with anton failed"
# despite tokens minting fine. "*" is safe: uvicorn only ever receives traffic
# from Caddy over the container's internal network, never external clients direct.
# The "*" stays quoted so it survives both the litestream `sh -c` exec and the
# dev `bash -c` exec below without glob-expanding against /app.
set -euo pipefail

LITESTREAM_CONFIG=/app/litestream.yml
UVICORN_CMD="uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=\"*\""

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
    # bash -c so the quoted --forwarded-allow-ips="*" is shell-interpreted the
    # same way litestream's `sh -c` handles it above (no glob against /app).
    exec bash -c "$UVICORN_CMD"
fi
