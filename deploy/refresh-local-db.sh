#!/bin/bash
# Refresh the LOCAL test DB from the newest production snapshot, weekly (Mondays).
#
# The local DB (~/anton-data/shoe_deals.db) is only for testing, so it drifts
# from production. backup-prod.sh already pulls a consistent prod snapshot to
# ~/anton-data/backups/ every other day; this copies the newest one over the
# local DB. No network, no SSH, no B2 — it only reads files that job wrote.
#
# Safety:
#   - Refuses while anything has the local DB open (a running dev server would
#     keep writing to the replaced file's old inode, and its WAL would not match).
#   - Checks the snapshot (integrity_check + activities count) before touching
#     anything, and keeps the current local DB as a dated
#     `local-pre-refresh.bak` first (newest KEEP survive; nothing else is pruned).
#   - Removes the old DB's -wal/-shm so the new file never pairs with a stale WAL.
#   - COROS: the snapshot carries production's encrypted COROS tokens. The local
#     .env must NOT set production's COROS_TOKEN_KEY — if it could decrypt them,
#     the local poller would refresh the token, and COROS rotates refresh tokens,
#     so production would be logged out (INV-9's refresh-lock note). Set
#     ANTON_LOCAL_ENV to the local backend/.env and the script refuses when that
#     file sets COROS_TOKEN_KEY. Without the key, local COROS reads "reconnect
#     needed" — expected.
#   - Schema: run.py runs `alembic upgrade head` on boot, so a branch with newer
#     migrations upgrades the copy. A checkout BEHIND production's migrations
#     can't start on it ("Can't locate revision") — pull main first.
#
# Scheduling: launchd fires Mondays at 10:00, after the 09:30 backup job
# (deploy/com.anton.local-db-refresh.plist); a run missed while asleep fires on
# wake. If the dev server is up at that moment the run fails with a
# notification — stop the server and run it by hand.
#
# Install (laptop):
#   mkdir -p ~/anton-data/bin
#   cp deploy/refresh-local-db.sh ~/anton-data/bin/ && chmod +x ~/anton-data/bin/refresh-local-db.sh
#   sed "s|__HOME__|$HOME|g; s|__REPO__|$PWD|g" deploy/com.anton.local-db-refresh.plist \
#     > ~/Library/LaunchAgents/com.anton.local-db-refresh.plist
#   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.anton.local-db-refresh.plist
# Run once by hand:  ANTON_LOCAL_ENV=backend/.env ~/anton-data/bin/refresh-local-db.sh
# Uninstall:         launchctl bootout gui/$(id -u)/com.anton.local-db-refresh

set -euo pipefail

LOCAL_DB="${ANTON_LOCAL_DB:-$HOME/anton-data/shoe_deals.db}"
BACKUP_DIR="${ANTON_BACKUP_DIR:-$HOME/anton-data/backups}"
KEEP="${ANTON_REFRESH_KEEP:-4}"                    # pre-refresh copies retained (≈4 weeks)
STALE_DAYS=7                                       # warn: the backup job has probably stopped
SRC_SUFFIX="prod-auto.bak"                         # written by backup-prod.sh
OWN_SUFFIX="local-pre-refresh.bak"                 # retention only ever touches files with this suffix

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
fail() {
    log "FAILED: $*"
    osascript -e "display notification \"$*\" with title \"Anton local DB refresh failed\"" >/dev/null 2>&1 || true
    exit 1
}

if [ -n "${ANTON_LOCAL_ENV:-}" ] && [ -f "$ANTON_LOCAL_ENV" ] \
    && grep -Eq '^[[:space:]]*COROS_TOKEN_KEY=[^[:space:]#]' "$ANTON_LOCAL_ENV"; then
    fail "local .env sets COROS_TOKEN_KEY — a local poller could rotate prod's COROS token"
fi

src="$(ls -1t "$BACKUP_DIR"/shoe_deals.db.*-"$SRC_SUFFIX" 2>/dev/null | head -1 || true)"
[ -n "$src" ] || fail "no *-$SRC_SUFFIX snapshot in $BACKUP_DIR"
age_d=$(( ($(date +%s) - $(stat -f %m "$src")) / 86400 ))
[ "$age_d" -le "$STALE_DAYS" ] || log "WARNING: newest snapshot is ${age_d}d old — is backup-prod.sh running?"

# One path per lsof call: lsof exits non-zero when ANY named file is missing,
# so passing a non-existent -wal alongside would hide an open DB.
for f in "$LOCAL_DB" "$LOCAL_DB-wal"; do
    if [ -e "$f" ] && lsof -- "$f" >/dev/null 2>&1; then
        fail "local DB is open (dev server running?) — stop it and run refresh-local-db.sh by hand"
    fi
done

# immutable=1: read the WAL-mode snapshot without creating -shm/-wal beside it.
ro="file:$src?immutable=1"
check="$(sqlite3 "$ro" 'PRAGMA integrity_check;' 2>&1 | head -1 || true)"
[ "$check" = "ok" ] || fail "integrity_check on $(basename "$src"): $check"
activities="$(sqlite3 "$ro" 'SELECT COUNT(*) FROM activities;' 2>/dev/null || echo 0)"
[ "$activities" -gt 0 ] || fail "$(basename "$src") has no activities"

keep="$BACKUP_DIR/shoe_deals.db.$(date +%Y-%m-%d)-$OWN_SUFFIX"
if [ -e "$keep" ]; then
    # A same-day re-run: today's copy holds the pre-refresh DB; don't overwrite it.
    log "today's $(basename "$keep") already exists — not overwriting it"
elif [ -e "$LOCAL_DB" ]; then
    # Nothing has the DB open (checked above), so sqlite3 .backup folds any WAL in.
    sqlite3 "$LOCAL_DB" ".backup '$keep'" || fail "could not back up the local DB"
    rm -f "$keep-wal" "$keep-shm"                  # empty once sqlite3 has exited
    log "kept current local DB as $(basename "$keep")"
fi

# Copy beside the target, then rename: the DB path is never half-written.
tmp="$LOCAL_DB.refresh-partial"
trap 'rm -f "$tmp"' EXIT
cp "$src" "$tmp"
rm -f "$LOCAL_DB-wal" "$LOCAL_DB-shm"
mv "$tmp" "$LOCAL_DB"
log "ok: local DB ← $(basename "$src") ($activities activities, snapshot ${age_d}d old)"

# Retention: newest $KEEP pre-refresh copies survive; every other file is untouched.
ls -1t "$BACKUP_DIR"/shoe_deals.db.*-"$OWN_SUFFIX" 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f "$old" "$old-wal" "$old-shm" && log "pruned $(basename "$old")"
done
