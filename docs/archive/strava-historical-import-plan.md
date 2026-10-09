# Strava Historical Import — Implementation Plan

**Project:** running-shoe-deals (FastAPI + SQLAlchemy + SQLite backend, React 18 frontend, Alembic migrations, MCP server at `/mcp/`)
**Source data:** Strava bulk export at `~/workspace/export_33354574/`
**Goal:** Import 8 years of Strava history (694 runs, Aug 2018 – Jul 2026) into a new table, backfill shoe attribution via the `Activity Gear` column, deduplicate against runs already logged via the COROS sync, and keep owned-shoe mileage consistent.

---

## 0. Data facts (verified against the actual export — do not re-derive, trust these)

- `activities.csv`: 929 rows, 694 with `Activity Type == "Run"`. Other types (Ride 71, Walk 67, Weight Training 58, ...) are imported too but never attributed to shoes.
- **Gear coverage:** 662 of 694 runs have `Activity Gear` populated. The 32 gaps are mostly 2018–2022 legacy runs (20) plus 12 scattered across 2024–2026.
- **Gear name format:** `"{Brand} {Model}"`, e.g. `"Adidas Evo SL Teal"`, `"PUMA DNE3"`, `"Mizuno Neo Zen"`. Duplicate pairs already exist as distinct gear entries (Evo SL / Evo SL Teal / Evo SL Purple / Evo SL ATR; Neo Zen / Neo Zen Mint) — no date-range splitting needed.
- `shoes.csv` exists in the export with Brand/Model per shoe but **no lifetime distance column** — it cannot be used as a mileage checksum. Reconciliation is done against the app's own data instead (§5). Note: `"Neo Zen "` has a trailing space in shoes.csv; always `.strip()` gear strings.
- **CSV has duplicate column headers.** `Elapsed Time`, `Distance`, `Max Heart Rate`, `Relative Effort`, `Commute` each appear twice. With pandas, the second occurrence becomes `Distance.1` etc. Semantics:
  - `Distance` (first) = kilometers, 2 decimals → **use this** for `distance_km`
  - `Distance.1` = meters (float)
  - `Elapsed Time` (first, int) and `Elapsed Time.1` = seconds; `Moving Time` = seconds → **use Moving Time for pace**
  - `Max Heart Rate` (first) vs `Max Heart Rate.1` — keep the second (device summary); `Average Heart Rate` appears once
- **`Activity Date` is UTC** in format `"Jul 2, 2026, 11:08:07 PM"`. The app's run dates are America/Toronto. **145 of 694 runs land on a different calendar date after conversion** (evening runs). Conversion is mandatory before any dedup matching:
  ```python
  ts_utc = pd.to_datetime(raw, format="%b %d, %Y, %I:%M:%S %p", utc=True)
  ts_local = ts_utc.tz_convert("America/Toronto")
  ```
- `Average Heart Rate` missing on 18 runs — nullable.
- `Filename` (e.g. `activities/20273873902.fit.gz`) present on all runs — store it; enables future per-second FIT analysis without re-requesting the archive.
- `Activity ID` is Strava's stable unique ID — natural key for idempotent re-imports.

---

## 1. Schema (one Alembic migration)

### 1.1 New table: `strava_activities`

Canonical import of every activity (all types). Raw-ish: light normalization only, so richer features can re-derive later.

| column | type | notes |
|---|---|---|
| `id` | Integer PK | |
| `strava_activity_id` | BigInteger, unique, indexed, not null | `Activity ID` |
| `activity_type` | String, indexed | Run / Ride / Walk / ... |
| `name` | String | `Activity Name` |
| `description` | Text, nullable | `Activity Description` |
| `started_at_utc` | DateTime (UTC) | parsed `Activity Date` |
| `started_at_local` | DateTime | America/Toronto conversion |
| `run_date` | Date, indexed | local calendar date — the dedup/match key |
| `distance_km` | Float | first `Distance` column |
| `moving_time_s` | Integer | |
| `elapsed_time_s` | Integer | |
| `avg_hr` | Integer, nullable | rounded `Average Heart Rate` |
| `max_hr` | Integer, nullable | |
| `avg_pace_s_per_km` | Integer, nullable | `moving_time_s / distance_km`, null if distance < 0.5 km |
| `elevation_gain_m` | Float, nullable | |
| `avg_cadence` | Float, nullable | |
| `calories` | Float, nullable | |
| `gear_name` | String, nullable, indexed | stripped `Activity Gear` |
| `fit_filename` | String, nullable | `Filename` |
| `grade_adjusted_distance_m` | Float, nullable | |
| `raw_json` | JSON/Text | full CSV row as dict — the "ingest raw, model later" escape hatch |
| `created_at` | DateTime | |

Store pace as **seconds per km** (int) in this table; format to `"M:SS/km"` only at the boundary when writing to `runs`/MCP, matching the existing convention.

### 1.2 New table: `strava_gear_mappings`

| column | type | notes |
|---|---|---|
| `id` | Integer PK | |
| `gear_name` | String, unique, not null | exact stripped Strava string |
| `owned_shoe_id` | FK → owned_shoes.id, **nullable** | null = "known but unmapped" (e.g. shoes owned before the tracker, retired and deleted, or deliberately skipped) |

Nullable mapping matters: unmapped gear still imports into `strava_activities`; it just doesn't backfill a shoe run.

### 1.3 Changes to the existing runs table (`shoe_runs` or equivalent — check the model)

Add:
- `source` — String, not null, server_default `'manual'`. Values: `'manual' | 'coros' | 'strava'`. Backfill existing rows: rows created by `confirm_coros_run` / the COROS sync → `'coros'` if distinguishable (e.g. via `coros_activity_id` if that column exists), else leave `'manual'`.
- `strava_activity_id` — BigInteger, nullable, unique. Set on runs matched to or created from Strava. This is the idempotency guard: a run row can be linked to at most one Strava activity and vice versa.

Do **not** create a separate link table — a nullable FK-ish column is enough for a personal app.

---

## 2. Importer service: `app/services/strava_import.py`

Follow the existing service-extraction pattern from the refactor. Pure functions where possible; the CLI/endpoint is a thin wrapper.

```
parse_activities_csv(path) -> list[StravaActivityRow]   # handles dup headers, tz, stripping
upsert_strava_activities(rows, session) -> ImportStats  # idempotent on strava_activity_id
```

Parsing rules:
- Read with pandas; access duplicate columns via the `.1` suffix convention (add a unit test asserting `Distance` ≈ `Distance.1 / 1000` on a sample row to guard against Strava reordering columns in future exports).
- `gear_name = row["Activity Gear"].strip() or None`
- Skip nothing: import all 929 activities. `activity_type` filtering happens downstream.
- Upsert semantics: on conflict with existing `strava_activity_id`, update fields (allows re-running after a fresh export) — never duplicate.

CLI entry point (simplest for a one-shot import): `python -m app.scripts.import_strava --csv path/to/activities.csv`.

---

## 3. Gear mapping seed: `app/scripts/seed_gear_mappings.py`

1. `SELECT DISTINCT gear_name FROM strava_activities WHERE gear_name IS NOT NULL` (expect 22 values).
2. Fetch all `owned_shoes` (all statuses, not just active — history includes retired shoes).
3. Auto-match by normalized name: lowercase, strip brand prefixes (`adidas|nike|mizuno|puma|new balance|under armour`), collapse whitespace, compare against owned shoe name/nickname the same way. Expect near-total auto-match given the rotation names (Evo SL Teal, DNE3, Neo Zen Mint, ...).
4. Print the proposed mapping table and **require interactive confirmation** (or a `--yes` flag) before writing. Unmatched gear gets inserted with `owned_shoe_id = NULL` and listed clearly so leftovers can be mapped by hand later (likely candidates: long-retired shoes like Winflo 8, Zoom Fly 5, Fresh Foam X More that may not exist in `owned_shoes`).
5. Idempotent: existing mappings are never overwritten by the auto-matcher.

---

## 4. Dedup + backfill: `app/services/strava_backfill.py`

The core invariant: **every physical run exists at most once in the runs table**, regardless of how many systems recorded it.

### 4.1 Matching pass (link, don't create)

For each `strava_activities` row with `activity_type == 'Run'` and `strava_activity_id` not yet linked:

1. Candidate existing runs: same `run_date` (local!) and `abs(distance_km_diff) <= 0.1` — identical tolerance to the COROS sync protocol.
2. If exactly one candidate → link (`runs.strava_activity_id = ...`), regardless of which shoe it's logged to (the human-confirmed COROS assignment wins over the Strava gear column on conflicts — but **log the conflict** in the report).
3. If multiple candidates (two runs same day, similar distance) → tie-break on closest distance, then closest start time if the runs table has one; if still ambiguous, leave unlinked and flag for manual review. Do not guess.
4. Widen pass for stragglers: `run_date ± 1 day` with same distance tolerance, flagged as "date-shift match" in the report — catches any historical logging done before the timezone rules were pinned down. These require manual confirmation, never auto-link.

### 4.2 Backfill pass (create)

For each still-unlinked Strava run:
- gear mapped to an `owned_shoe_id` → create a run row: `source='strava'`, `strava_activity_id`, `run_date` (local), `distance_km`, `avg_pace` formatted `"M:SS/km"`, `avg_hr` in the dedicated fields (per house rules — never in notes), `notes = NULL`.
- gear unmapped or absent → skip (remains queryable in `strava_activities`; can be attributed later, optionally with the pace+distance heuristic from the COROS protocol as a suggestion engine — out of scope for v1).

### 4.3 Two-phase execution — dry run is mandatory

`--dry-run` (default) produces a report and writes nothing:
- matched: N (with shoe-conflict sublist)
- date-shift candidates: N (manual review list)
- ambiguous: N
- will create: N runs across M shoes, per-shoe km deltas
- skipped (unmapped gear / no gear): N

`--commit` executes inside a single transaction. Review the dry-run output before committing — this is the checkpoint where mistakes are free.

---

## 5. Mileage reconciliation

After commit, shoe mileage must equal the sum of its runs — but check how `owned_shoes.current_mileage` (or equivalent) works first:

- **If mileage is a derived value** (computed from runs): nothing to do beyond a sanity report.
- **If mileage is a stored counter incremented by `log_run_to_shoe`:** the backfill script must increment it identically for created runs, **and** watch for shoes that were created with a non-zero starting mileage meant to represent pre-tracker history. For those, the Strava backfill now *replaces* that estimate with real runs — the starting offset must be reduced or zeroed or km will be double-counted. The dry-run report must surface, per shoe: `current_mileage`, `sum(existing runs)`, implied starting offset, `sum(backfill runs)`, and proposed final mileage. **Any shoe where the implied offset overlaps the backfill period gets flagged for a per-shoe decision — do not auto-resolve.**
- Cross-check: per-shoe `sum(distance_km)` in `strava_activities` grouped by gear vs. final app mileage. Deltas should equal (a) runs logged in the app but never on Strava, plus (b) unmatched/ambiguous rows. Anything else is a bug.

Known checkpoints from live tracking to validate against: DNE3 ≈ 600 km territory, Evo SL Teal > 300 km.

---

## 6. MCP exposure (after data is in and reconciled)

New tools/resources on the existing FastMCP server:

1. **`get_training_summary(period: str)`** — weekly or monthly aggregates over `strava_activities` (runs only): total km, run count, avg pace, avg HR, elevation. Cheap SQL GROUP BY.
2. **`get_personal_bests()`** — fastest average pace at distance bands (5k ±0.3, 10k ±0.5, half ±1, full ±1.5) computed from moving time. Note these are *average-pace-for-whole-activity* bests, not true segment PBs — name/describe accordingly.
3. **Resource template `strava://runs/{year}/{month}`** — the period-scoped run list, so a chat can pull one month without flooding context.
4. Extend the existing shoe stats path so `get_shoe_runs` lifetime averages now naturally include backfilled history (they will automatically if computed from the runs table — verify).

Register these in the same pattern as existing tools; they should also become available to Son of Anton for free via the existing list_tools/call_tool discovery.

---

## 7. Testing

- Parser: fixture CSV with duplicate headers, a UTC-date-shift row (e.g. 11:08 PM UTC → previous-evening local), missing HR, missing gear, trailing-space gear.
- Matcher: exact match, distance-tolerance match, multi-candidate ambiguity, date-shift widening, shoe-conflict logging.
- Backfill idempotency: running the full pipeline twice produces zero new rows and zero mileage change (assert on `strava_activity_id` uniqueness).
- Mileage: property-style check that post-commit `mileage == sum(runs) + approved_offset` for every shoe.

---

## 8. Execution order for the Claude Code session

1. Migration: `strava_activities`, `strava_gear_mappings`, `runs.source` + `runs.strava_activity_id` (+ backfill `source` for existing rows). Run `alembic upgrade head`.
2. Implement + test the CSV parser (§2). Run the import; verify 929 rows, 694 runs, spot-check the Jul 2 evening run lands on Jul 2 local.
3. Seed gear mappings (§3); manually resolve any `NULL` mappings that should map.
4. Implement matcher + backfill (§4) with `--dry-run`. **Stop and review the report** — especially shoe conflicts, date-shift candidates, and the mileage reconciliation table (§5).
5. `--commit`. Re-run dry-run to confirm it now reports zero pending changes (idempotency proof).
6. Verify shoe mileages in the UI against known checkpoints (DNE3, Evo SL Teal).
7. Add MCP tools/resources (§6) + tests.
8. Commit in logical chunks: migration → importer → mapping → backfill → MCP.

**Out of scope for v1 (explicitly):** `.fit.gz` parsing, non-run shoe attribution, AI-suggested attribution for the 32 gear-less runs, Strava API live sync. All become easy follow-ups once this lands.
