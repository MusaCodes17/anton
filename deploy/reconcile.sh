#!/bin/bash
# Anton DB reconciliation — RA1.5 cutover checkpoint (runbook §7 steps 1 & 5).
#
# The E4 discipline (design_decisions.md E4) requires that a DB move be proven
# lossless: the same counts before and after. This script pins the *definitions*
# of the four canonical metrics so the before/after comparison is unambiguous,
# and adds the integrity + FK + alembic-head checks you want confirmed before
# copying the live DB to the host.
#
# The four canonical metrics (as used in REMOTE_ACCESS_PLAN.md §7):
#   activities  = COUNT(*) FROM activities                         (all sport types)
#   runs        = COUNT(*) FROM activities WHERE activity_type='Run'
#   attributed  = COUNT(*) FROM shoe_runs                          (runs tied to a shoe)
#   run_km      = ROUND(SUM(distance_km),1) WHERE activity_type='Run'
#
# Usage:
#   ./reconcile.sh <db_path>            # print the canonical report for one DB
#   ./reconcile.sh <db_a> <db_b>        # compare two DBs; exit 1 on ANY mismatch
#
# Cutover procedure (runbook §7):
#   1. On the laptop, snapshot the baseline:
#        ./reconcile.sh ~/anton-data/shoe_deals.db | tee /tmp/anton-baseline.txt
#   2. Copy the DB up; boot the container (alembic upgrade head is a no-op if heads match).
#   3. On the host, compare the copied DB against the baseline path:
#        ./reconcile.sh /path/to/baseline-copy.db /data/shoe_deals.db
#      A clean "MATCH" (exit 0) is runbook step 5 satisfied.

set -euo pipefail

if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "Error: sqlite3 CLI not found on PATH." >&2
    exit 1
fi

# Emit the canonical metrics + head for one DB as "key<TAB>value" lines.
_metrics() {
    local db="$1"
    if [ ! -f "$db" ]; then
        echo "Error: database not found: $db" >&2
        exit 1
    fi
    printf 'activities\t%s\n'  "$(sqlite3 "$db" 'SELECT COUNT(*) FROM activities;')"
    printf 'runs\t%s\n'        "$(sqlite3 "$db" "SELECT COUNT(*) FROM activities WHERE activity_type='Run';")"
    printf 'attributed\t%s\n'  "$(sqlite3 "$db" 'SELECT COUNT(*) FROM shoe_runs;')"
    printf 'run_km\t%s\n'      "$(sqlite3 "$db" "SELECT ROUND(SUM(distance_km),1) FROM activities WHERE activity_type='Run';")"
    printf 'alembic_head\t%s\n' "$(sqlite3 "$db" 'SELECT version_num FROM alembic_version;')"
}

# Integrity + FK checks (advisory — printed, not part of the match comparison).
_integrity() {
    local db="$1"
    local ic fk
    ic="$(sqlite3 "$db" 'PRAGMA integrity_check;')"
    fk="$(sqlite3 "$db" 'PRAGMA foreign_key_check;')"
    printf 'integrity_check\t%s\n' "$ic"
    if [ -z "$fk" ]; then
        printf 'foreign_key_check\tclean\n'
    else
        printf 'foreign_key_check\tVIOLATIONS FOUND:\n%s\n' "$fk"
    fi
}

_report() {
    local db="$1"
    echo "== $db =="
    _metrics "$db" | while IFS=$'\t' read -r k v; do printf '  %-18s %s\n' "$k" "$v"; done
    _integrity "$db" | while IFS=$'\t' read -r k v; do printf '  %-18s %s\n' "$k" "$v"; done
    echo ""
}

case $# in
    1)
        _report "$1"
        ;;
    2)
        _report "$1"
        _report "$2"
        # Compare the five canonical metric lines; integrity is advisory only.
        a="$(_metrics "$1")"
        b="$(_metrics "$2")"
        if [ "$a" = "$b" ]; then
            echo "RECONCILE: MATCH — all canonical metrics + alembic head identical."
            exit 0
        else
            echo "RECONCILE: MISMATCH" >&2
            diff <(printf '%s\n' "$a") <(printf '%s\n' "$b") >&2 || true
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 <db_path> [<db_path_b>]" >&2
        exit 2
        ;;
esac
