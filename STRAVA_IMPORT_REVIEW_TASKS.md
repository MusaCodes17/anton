# Strava Import — Code Review Fixes & Refactors

Tasks from a post-implementation review of the Strava historical import
(see `strava-historical-import-plan.md` for the original plan). Work through
them **in order** — Tasks 1–3 are runtime bugs that block the COROS sync and
review workflows; the rest are refactors and optimizations.

For each task: implement, add/update tests where indicated, run the full test
suite (`pytest backend/tests -q` from the repo root, venv activated), and make
one commit per task with a message referencing the task number
(e.g. `fix(mcp): T1 log_run_to_shoe NameError + triplicated threshold block`).

Do not change behavior beyond what each task describes. If a task turns out to
be inapplicable or already fixed, say so and skip it — don't force a change.

---

## Task 1 — Fix `log_run_to_shoe` in `backend/app/mcp_server.py` (CRITICAL)

**Bug:** the tool is currently broken — every call raises `NameError`, is
swallowed by the outer `except`, and returns `{"success": False}`.

Two problems:
1. The 600/700/800km threshold-check block is **pasted three times** verbatim.
   Keep exactly one.
2. The return statement references `checkpoint_reached` and `new_checkpoint`,
   which are never defined. Use the `RunLogResult` returned by
   `rotation.log_run`: `result.checkpoint_reached` and `result.checkpoint_km`.

Acceptance:
- Single threshold block; no undefined names.
- Response shape unchanged: `checkpoint_reached`, `checkpoint_km`,
  `threshold_crossed`, `threshold_message` keys all still present.
- Add a regression test (the MCP tool wraps `rotation.log_run`; test at
  whichever layer is practical — at minimum, a test that importing and calling
  the underlying path returns checkpoint info correctly).

## Task 2 — Fix `draft_shoe_review` in `backend/app/mcp_server.py`

**Bug:** calls `_compute_lifetime_stats(db, owned_shoe_id)`, which does not
exist (`NameError` before the sampling call ever happens), and then treats the
result as a dict (`stats.get("total_runs", 0)` etc.).

Fix: call `rotation.compute_lifetime_stats(db, owned_shoe_id)` and use
attribute access on the `LifetimeStats` dataclass (`stats.total_runs`,
`stats.lifetime_avg_pace`, `stats.lifetime_avg_hr`).

## Task 3 — Fix Step 6 of the `sync_coros_runs` MCP prompt (`backend/app/mcp_server.py`)

**Bug:** the prompt instructs the agent to log confirmed runs via
`log_run_to_shoe` with `source: "coros"` — but that tool has **no `source`
parameter** and never sets `coros_activity_id`. Runs logged that way land as
`source='manual'` with no COROS ID, breaking dedup matching and source
attribution.

Fix: rewrite Step 6 to call `confirm_coros_run` with `coros_activity_id`,
`owned_shoe_id`, `date`, `distance_km`, `avg_pace`, `avg_hr`. Also fix the
"General rules" line that says run details come from
`fetch_unsynced_coros_runs` (they come from `querySportRecords` per Step 1).

## Task 4 — Resolve the ShoeRun write-path contradiction

`backend/app/services/rotation.py` — `log_run`'s docstring claims it is
"THE only code path that writes a ShoeRun", but
`backend/app/services/strava_backfill.py` → `execute_backfill` now
deliberately writes `ShoeRun` rows directly (to control the mileage policy
instead of blindly incrementing).

Preferred fix: refactor so the invariant holds again. Add a parameter to
`rotation.log_run` (e.g. `increment_mileage: bool = True`, and
`strava_activity_id: Optional[int] = None`, `commit: bool = True`) so
`execute_backfill` can route through it while applying its own mileage policy
afterward. If that gets awkward, the fallback is to update the docstring to
explicitly name `execute_backfill` as the one sanctioned exception — but try
the refactor first. Keep the existing backfill tests green either way.

## Task 5 — Per-shoe mileage policy override on commit

`backend/app/scripts/backfill_strava.py` + `strava_backfill.py`: the dry run
flags shoes whose starting offset overlaps the backfill ("per-shoe decision"
per §5 of the plan), but `--commit` applies **one global policy**. Add a
repeatable CLI flag, e.g.:

    python -m app.scripts.backfill_strava --commit \
        --mileage-policy preserve \
        --shoe-policy 5=offset-zero --shoe-policy 12=add

`execute_backfill` gains an optional `per_shoe_policies: dict[int, str]`
argument that overrides the global policy for those shoe ids. Validate policy
names against `MILEAGE_POLICIES`. Add tests: one shoe under global preserve +
one overridden to offset-zero in the same commit.

## Task 6 — Kill the N+1 query pattern in `plan_backfill`

`strava_backfill.py` currently issues 1–2 queries **per Strava run** (~1,400
queries for 694 runs). Load all unlinked `ShoeRun` rows once
(`strava_activity_id IS NULL`), index them in memory by `run_date`
(a `dict[date, list[ShoeRun]]`), and do exact/±1-day candidate lookups against
that dict. Behavior must be identical — all existing matcher tests stay green
unchanged. This also makes the matching logic unit-testable without query
counting.

## Task 7 — Report ALL date-shift candidates

`plan_backfill` currently records only `shift[0]` when the ±1-day widening
finds candidates, even if several exist. Change the date-shift path to carry
every candidate (mirror the `ambiguous` dict shape: strava id, run_date,
distance, `candidate_run_ids`) so manual review sees the full picture. Update
`backfill_strava.py`'s report printer and the existing date-shift test.

## Task 8 — Add a `strava` source badge to `shoe_runs_resource`

`mcp_server.py` → `shoe_runs_resource` renders `"🤖 coros"` or `"✍ manual"`;
backfilled runs (`source='strava'`) currently fall through to "manual". Add a
distinct badge (e.g. `"🟠 strava"`) and make the mapping a small dict with a
sane default instead of a ternary.

## Task 9 — Clean up dead/unsafe code in `plan_backfill`

- The `if s.run_date is None or s.distance_km is None: pass` block is a no-op —
  remove it.
- A Strava run with mapped gear but **missing `run_date` or `distance_km`**
  currently flows into `to_create`, and `ShoeRun.run_date` /
  `ShoeRun.distance_km` are non-nullable — the commit would blow up.
  Skip such rows explicitly into a new report bucket
  (`skipped_missing_data: list[int]`) and print it in the CLI report. Add a
  test.

## Task 10 — Low-priority tidying (do last; skip if time-boxed)

- `strava_stats.training_summary` aggregates in Python. Fine at ~700 runs;
  optionally convert the monthly path to a SQL `GROUP BY` (weekly ISO-week
  bucketing can stay in Python). Only do this if it doesn't complicate the
  code — readability wins at this scale.
- The superseded `migrate_*.py` scripts in `backend/` root predate Alembic —
  move them into `backend/legacy_migrations/` so the root stays clean. Pure
  file moves, no code changes.

---

## Definition of done

- All tasks 1–9 committed individually, full test suite green.
- `python -m app.scripts.backfill_strava` (dry run) still produces a sane
  report against the real DB.
- Manually verify via MCP Inspector or Claude Desktop that `log_run_to_shoe`
  and `draft_shoe_review` now return `success: true` paths.
