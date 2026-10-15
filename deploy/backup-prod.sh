#!/bin/bash
# Pull a consistent snapshot of the PRODUCTION DB to the laptop, every other day.
#
# Why this exists alongside Litestream (RA1.4): Litestream keeps 14 days of
# point-in-time history in B2, but restoring needs the B2 credentials and the
# litestream binary, and anything older than 14 days is gone. This keeps a
# plain, offline, independently readable copy on the laptop for longer
# (KEEP files ≈ 30 days at every-other-day) — a second, boring recovery path.
#
# How: over SSH, `sqlite3 .backup` runs INSIDE the app container (the Hetzner
# host has no sqlite3 — see restore.sh), the copy is streamed back over stdout,
# then checked locally (integrity_check + activities count) before it replaces
# nothing. Never a plain cp of the live DB: .backup is consistent under WAL.
# Read-only on production: no second app process, no writes (INV-9 is safe).
#
# Scheduling: launchd fires daily (deploy/com.anton.prod-backup.plist); the
# script skips unless the newest auto snapshot is older than MIN_AGE_H, which
# gives "every other day" while still catching up after the laptop was asleep.
#
# Install (laptop):
#   mkdir -p ~/anton-data/bin
#   cp deploy/backup-prod.sh ~/anton-data/bin/ && chmod +x ~/anton-data/bin/backup-prod.sh
#   sed "s|__HOME__|$HOME|g; s|__HOST__|<ssh-alias>|g" deploy/com.anton.prod-backup.plist \
#     > ~/Library/LaunchAgents/com.anton.prod-backup.plist
#   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.anton.prod-backup.plist
# Run once by hand:  ANTON_BACKUP_HOST=<ssh-alias> FORCE=1 ~/anton-data/bin/backup-prod.sh
# Uninstall:         launchctl bootout gui/$(id -u)/com.anton.prod-backup
#
# SSH must work non-interactively (key in the macOS keychain or no passphrase):
# BatchMode makes a prompt fail loudly instead of hanging the job.

set -euo pipefail

HOST="${ANTON_BACKUP_HOST:?set ANTON_BACKUP_HOST to the production ssh alias}"
REMOTE_DIR="${ANTON_REMOTE_DIR:-anton}"            # compose project dir, relative to the remote home
BACKUP_DIR="${ANTON_BACKUP_DIR:-$HOME/anton-data/backups}"
KEEP="${ANTON_BACKUP_KEEP:-15}"                    # auto snapshots retained (≈30 days)
MIN_AGE_H="${ANTON_BACKUP_MIN_AGE_H:-44}"          # 48 h cadence minus slack for launch-time drift
SUFFIX="prod-auto.bak"                             # retention only ever touches files with this suffix

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
fail() {
    log "FAILED: $*"
    osascript -e "display notification \"$*\" with title \"Anton prod backup failed\"" >/dev/null 2>&1 || true
    exit 1
}

mkdir -p "$BACKUP_DIR"

newest="$(ls -1t "$BACKUP_DIR"/shoe_deals.db.*-"$SUFFIX" 2>/dev/null | head -1 || true)"
if [ -z "${FORCE:-}" ] && [ -n "$newest" ]; then
    age_h=$(( ($(date +%s) - $(stat -f %m "$newest")) / 3600 ))
    if [ "$age_h" -lt "$MIN_AGE_H" ]; then
        log "skip: newest snapshot $(basename "$newest") is ${age_h}h old (< ${MIN_AGE_H}h)"
        exit 0
    fi
fi

dest="$BACKUP_DIR/shoe_deals.db.$(date +%Y-%m-%d)-$SUFFIX"
partial="$dest.partial"
trap 'rm -f "$partial"' EXIT

log "pulling snapshot from $HOST:$REMOTE_DIR"
ssh -o BatchMode=yes -o ConnectTimeout=20 "$HOST" \
    "cd '$REMOTE_DIR' && docker compose exec -T anton sh -s" > "$partial" <<'REMOTE' \
    || fail "ssh/backup step failed"
set -e
trap 'rm -f /tmp/anton-snap.db' EXIT
sqlite3 /data/shoe_deals.db ".backup /tmp/anton-snap.db"
cat /tmp/anton-snap.db
REMOTE

[ -s "$partial" ] || fail "empty snapshot"
check="$(sqlite3 "$partial" 'PRAGMA integrity_check;' 2>&1 | head -1 || true)"
[ "$check" = "ok" ] || fail "integrity_check: $check"
activities="$(sqlite3 "$partial" 'SELECT COUNT(*) FROM activities;' 2>/dev/null || echo 0)"
[ "$activities" -gt 0 ] || fail "snapshot has no activities"

mv "$partial" "$dest"
log "ok: $(basename "$dest") ($(du -h "$dest" | cut -f1), $activities activities)"

# Retention: newest $KEEP auto snapshots survive; manual .bak files are never touched.
ls -1t "$BACKUP_DIR"/shoe_deals.db.*-"$SUFFIX" | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f "$old" && log "pruned $(basename "$old")"
done
