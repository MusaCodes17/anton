# TRAINING_DEPTH_PLAN — R2.7 Training & Activity Depth

**Status:** planning (awaiting confirmation before code)
**Roadmap:** `docs/roadmap.md` §R2.7 (eight sub-items, user feature requests 2026-07-07).
**Gates:** R2.2 (schema authority) — done, so every column/table below is born as a clean Alembic migration.
**Discipline:** E4 migration bar (reversible downgrade, named backup in `~/anton-data/backups/`, pre/post reconciliation), INV-1 mileage ledger, C9 confirmation gate, backend-before-UI, one commit per §-numbered task, suite green each session.

This is the sibling of `SECURITY_PASS_PLAN.md`: the §-numbered contract the executing sessions follow. It supersedes nothing; it sequences R2.7.

---

## 1. Scope & non-goals

**In scope:** activity tagging vocabulary; richer COROS field capture; a correctness fix to the PB algorithm; two Training-tab display changes; an athlete-fitness snapshot table + card; an activity detail/edit view with shoe reassignment and race promotion; a past-race→activity link; COROS-name tag inference.

**Non-goals:** no plan *generation* (advisory only lives in R3.6); no new ingestion source (FIT-file detail is R5.4); no scheduling (R4); no change to the deals domain. The `activity_tag` and (future) `shoe_type` vocabularies stay **independent backend-owned lists** — this milestone does not merge them (B1 domain independence holds).

## 2. Current-state facts (verified against code, 2026-07-07)

- `Activity` **already has**: `name`, `description`, `moving_time_s`, `elapsed_time_s`, `elevation_gain_m`, `avg_cadence`, `calories`, `avg_pace_s_per_km`, `grade_adjusted_distance_m`, `raw_json`. → T1 adds only 4 columns; T2 is mostly *populating existing* columns the COROS path discards.
- `services/activities.py` `UnifiedActivity` seam exposes `moving_time_s`, `avg_pace_s_per_km`, `avg_hr`, `elevation_m`, `name`, `shoe`, `strava_activity_id`, `shoe_run_id` — but **not** `elapsed_time_s`, `activity_tag`, `training_load`, `training_focus`, `best_km_pace_s`. T3 needs `activity_tag` + `elapsed_time_s` through this seam.
- `services/strava_stats.py` `personal_bests()` iterates `unified_activities`, bands by distance, picks min `_effective_moving_s`. No tag/elapsed exclusion today — that is exactly the T3 bug.
- `services/coros.py` `confirm_run(...)` has a **fixed keyword signature** (`coros_activity_id, owned_shoe_id, run_date, distance_km, avg_pace, avg_hr, notes`) and delegates to `rotation.log_run(...)`. T2 must widen both, or write the extra fields onto the `Activity` inside the sanctioned path — **never a second write path** (INV-2).
- `training_summary(db, period)` takes **no** date range; `/api/training/summary` (`routers/training.py:59`) likewise. `/api/activities` service takes `year/month/shoe_id/min_distance_km/limit/offset` — **not** `date_from/date_to`. → T4b's "already accepts date_from/date_to" claim is **wrong**; T4b includes adding them (see §Discovery D2).
- `PlannedRace` has no `activity_id` FK (T7 adds it). No backend-served vocabulary endpoint exists yet (R2.4 not done) — T1 establishes the pattern R2.4 will mirror.

## 3. Discovery steps (do these first, record findings in the changelog)

- **D1 — COROS field availability (blocks T2 & T5).** Confirm which fields the *working* sync path (the Claude-Desktop `sync_coros_runs` agent via the COROS MCP — server-side `coros_client` is dormant, C6) actually returns per activity: `name`, `elevation_gain_m`, `moving_time_s`, `elapsed_time_s`, `avg_cadence`, `calories`, `training_load`, `training_focus`. For T5: which endpoint exposes athlete-level `vo2max`, `threshold_pace`, `race_predictions` (COROS `queryFitnessAssessmentOverview` / `queryTrainingLoadAssessment` are candidates — verify). If a field isn't reachable, it stays nullable and unpopulated; do not invent it.
- **D2 — activities date-range params.** Confirm `/api/activities` uses `year/month` (it does per code) and decide T4b's approach: add `date_from`/`date_to` to `activities.unified_activities(...)` + the router, or have the picker drive `year/month`. Recommendation: add real `date_from`/`date_to` (superset of year/month) since T4b and `training_summary` both want it.
- **D3 — `elapsed_time_s` population.** Verify existing rows have `elapsed_time_s` (Strava import path) so the T3 elapsed guard has data; if the COROS path never set it, the guard only helps Strava history until T2 lands (acceptable — tags are the primary filter).

## 4. Execution order & session sequencing

**Dependency spine:** T1 → T2 → T3 (schema foundation), then T4 / T5 / T6 in parallel, then T7 (needs T6), then T8 (needs T2). Suggested sessions:

- **Session 1 (foundation):** D1/D2/D3 discovery · §T1 (schema + vocabulary + seam) · §T2 (COROS population) · §T3 (PB fix). Three commits.
- **Session 2 (display + fitness):** §T4a · §T4b · §T5 (table + card + sync). Three–four commits.
- **Session 3 (edit + links):** §T6 (detail/edit + reassign + promote) · §T7 (race↔activity link) · §T8 (tag inference). Three commits.

Each task below = one `r2:` commit, backend + its tests before any consuming UI.

---

## 5. The tasks

### §T1 — Extend the Activity model + tag vocabulary + seam

**Migration** (E4): reversible Alembic revision adding four **nullable** columns to `activities`:
`activity_tag VARCHAR(30)`, `best_km_pace_s INTEGER`, `training_load FLOAT`, `training_focus VARCHAR(50)`. Downgrade drops them. Purely additive → low risk, but named backup + row-count reconciliation still required.

**Vocabulary (backend-owned, served):** module-level tuple in a pure helper (e.g. `app/utils/activity_tags.py` or `services/activities.py`):
`Easy · Long Run · Recovery · Tempo · Intervals · Track · Workout · Trail · Parkrun · Race`.
Expose `GET /api/activities/tags` (or fold into an existing training meta endpoint) returning the list, so the frontend deletes any local copy — the pattern R2.4 mirrors for `shoe_type`. A comment marks the list as schema-grade ("do not grow casually", cites C9 for inference).

**Seam extension:** add `activity_tag` and `elapsed_time_s` to `UnifiedActivity` + populate them in `unified_activities()` (needed by T3). `best_km_pace_s`/`training_load`/`training_focus` surface where read (T5/T6) — add to the seam when first consumed, not speculatively.

**Tests:** migration up/down; vocabulary endpoint returns the list; a tagged activity round-trips through `unified_activities`.
**Commit:** `r2: R2.7 T1 — activity tags + fitness columns on activities`.

### §T2 — COROS sync field population (C9-compliant)

**What:** the confirm-and-log path populates the COROS-returned fields it currently discards. Extend the sanctioned path only — either widen `coros.confirm_run(...)` **and** `rotation.log_run(...)` with keyword-only optional params, or set the extra `Activity` fields inside `confirm_run` on the object `log_run` creates (return the Activity or its id). **No parallel write path** (INV-2); re-confirm stays an idempotent no-op (INV-5).

**Fields:** `name`, `description`(if any), `elevation_gain_m`, `moving_time_s`, `elapsed_time_s`, `avg_cadence`, `calories`, `training_load`, `training_focus` — gated on D1 availability.

**Confirmation protocol (C9):** when a COROS value can't map cleanly to Anton's vocabulary (proprietary training-load scale, an unmapped `training_focus`), the `sync_coros_runs` MCP prompt surfaces the best guess in the confirmation table — *"COROS labels this 'Marathon Pace' → tag `Tempo` — correct?"* — runner confirms/overrides; never silent. This extends the existing prompt, not a new tool.

**Tests:** `confirm_run` with the new fields writes them to the Activity; missing fields stay null; idempotent re-confirm unchanged.
**Commit:** `r2: R2.7 T2 — populate COROS activity fields on sync`.

### §T3 — Records algorithm fix (tag exclusion + elapsed guard)

**What:** `strava_stats.personal_bests()` gains eligibility filtering:
- **Tag filter:** `Intervals`/`Track` excluded; `Race`/`Parkrun` always included; `Easy/Long Run/Recovery/Tempo/Trail/Workout` included; untagged → elapsed guard.
- **Elapsed guard (untagged only):** `elapsed_time_s > 1.5 × moving_time_s` → excluded as stop-heavy.
- **Transparency:** add `pbs_excluded_count` + `pbs_excluded_reason` to the PB response so the UI can show "N excluded — tag them to reconsider".

**Where:** the filter lives in `personal_bests` over the seam (needs T1's `activity_tag`/`elapsed_time_s`). Frontend Records card shows the excluded-count note (small UI follow-on, same session or next).

**Tests (name the boundaries):** an `Intervals` session at 5 k distance does **not** set a 5 k PB; a `Race` does; an untagged stop-heavy run (elapsed > 1.5× moving) is excluded and counted; a clean untagged easy run still counts; the 1.5 ratio boundary is exact.
**Commit:** `r2: R2.7 T3 — PB eligibility (tag exclusion + elapsed guard)`.

### §T4 — Training tab display (two independent commits)

**T4a — month axis labels:** volume/mileage chart x-axis shows month labels ("Jun", "Jul") instead of week numbers; underlying data stays weekly. Frontend-only (recharts formatter). Desktop + ~380 px pass. `vite build` clean, 0 console errors.
**Commit:** `r2: R2.7 T4a — month axis labels on volume chart`.

**T4b — date-range picker:** header picker (default last 90 days, React state only) driving the activities list, volume chart, and summary card. Backend: add `date_from`/`date_to` to `activities.unified_activities` + `/api/activities`, and to `training_summary` + `/api/training/summary` (per D2). Backend params + tests land first; UI consumes them.
**Commit:** `r2: R2.7 T4b — date-range filtering (backend + Training tab)`.

### §T5 — Athlete fitness metrics

**Migration** (E4): new table `athlete_metrics` — `id PK`, `vo2max FLOAT`, `threshold_pace_s_per_km INTEGER`, `race_predictions JSON` (`{"5.0":1234,...}`), `captured_at DATETIME` (server-stamped). Append-only snapshots (one per sync); no update-in-place.
**Sync:** written on each COROS sync (path per D1). If server-side `coros_client` can't reach the fitness endpoint, the `sync_coros_runs` agent prompt fetches + confirms them alongside runs (C6/C9).
**API:** `GET /api/training/fitness` → most recent snapshot (or `{configured:false}`-style empty when none — graceful degradation).
**UI:** Training-tab card (beside Records/Races): VO2 Max, threshold pace as "M:SS/km", race predictions (5k/10k/HM/marathon).
**Tests:** insert/read latest snapshot; empty state; pace formatting.
**Commit:** `r2: R2.7 T5 — athlete fitness metrics table + card`.

### §T6 — Activity edit & open

**Service:** `rotation.reassign_attribution(db, activity_id, new_shoe_id)` — deletes the existing `ShoeRun`, decrements the old shoe's `current_mileage`, increments the new shoe's, creates the new `ShoeRun` — **through the INV-1 ledger arithmetic** (reuse `log_run`/`delete_run` internals, not raw ORM). Idempotent if the shoe is unchanged.
**Endpoints:** `PATCH /api/activities/{id}` (partial: `activity_tag`, `name`, `description`); `POST /api/activities/{id}/reassign-shoe` (separate — different write semantics). A tag change re-evaluates PBs (T3 reads live, so no cache to bust).
**Promote to race:** when tag set to `Race`, offer "Add to races" → pre-fills a `PlannedRace` (date, distance, `result_time_s` from the activity, status `completed`), and sets the T7 FK.
**UI:** activity detail (slide-over or `/activities/:id`) — view all fields, edit tag/name/notes, shoe-picker reassignment, promote-to-race.
**Tests:** reassignment moves mileage correctly both shoes (ledger round-trip, INV-1); PATCH updates tag/name; promote creates a completed `PlannedRace`.
**Commit:** `r2: R2.7 T6 — activity detail/edit + shoe reassignment + race promotion`.

### §T7 — Past race ↔ activity link

**Migration** (E4): add `activity_id INTEGER NULL FK→activities.id` to `planned_races`. Reversible (drop column).
**Behavior:** completing a `PlannedRace` links it to the race Activity; T6's promote-to-race sets it automatically. Past-race rows on the Races card become tappable → open the T6 detail view.
**Tests:** FK nullable, set on promote, race row exposes the linked activity id.
**Commit:** `r2: R2.7 T7 — planned_races.activity_id link`.

### §T8 — Activity tag inference from COROS name

**What:** a pure helper `suggest_tag_from_name(name) -> Optional[str]` implementing the case-insensitive keyword map (interval/repeat→Intervals; long→Long Run; tempo/threshold→Tempo; race/marathon→Race; parkrun→Parkrun; recovery/easy/jog→Easy; trail→Trail; track→Track; else None). The suggestion appears in the `sync_coros_runs` confirmation table; **never auto-applied** (C9) — runner confirms/overrides.
**Where:** helper next to the vocabulary (T1); prompt-text extension in `mcp_server.py`. No new endpoint.
**Tests:** each pattern maps as specified; no-match returns None; case-insensitivity.
**Commit:** `r2: R2.7 T8 — COROS-name tag inference (suggestion only)`.

---

## 6. Definition of done

- All eight tasks committed (one `r2:` commit each), suite green at each session end (record counts).
- Three migrations (T1, T5, T7) each E4-compliant: reversible, named backup, reconciled — recorded in the changelog.
- UI tasks (T4, T5 card, T6 view) pass desktop + ~380 px, `vite build` clean, 0 console errors.
- Vocabulary served from the backend (T1), consumed by the frontend, no independent copy.
- design_decisions gets an entry for the tag vocabulary (schema-grade list) and the PB eligibility rule; roadmap R2.7 row + §R2.7 breakdown updated; project_state refreshed. R2.7 T1/T5 noted as enabling R3.1/R3.4/R3.6 (already cited in the roadmap).

## 7. Open questions to resolve before/while executing

- **Q1 (D1):** exact COROS field coverage via the Desktop agent path — determines what T2/T5 can populate.
- **Q2 (D2):** `date_from/date_to` as the new activities filter (recommended) vs reusing `year/month`.
- **Q3:** activity detail as a slide-over vs a routed `/activities/:id` page (T6) — routed page recommended (deep-linkable, matches `/shoes/:id`).
- **Q4:** where the tag/vocabulary lives — `app/utils/activity_tags.py` (pure, importable by services + mcp) recommended, mirroring `app/utils/pace.py`.
