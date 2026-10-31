# Anton — Product Roadmap

**Generated:** 2026-07-04. **Last updated:** 2026-10-31 (**R12 — Lean COROS sync from Claude** scoped at the runner's request: plan in `docs/COROS_SYNC_LEAN_PLAN.md`, see §R12.) Prior update 2026-10-20 (**R11.6 built (B28) with R5.4.3 splits — R11 complete** on branch `r11-6-splits`: per-km splits with HR and elevation, long-run finishes in readiness; the runner reopened R5.4.3 and chose to include HR and elevation in the same build; migration `b9c0d1e2f3a4`.) Earlier the same day (**R11.7 built (B27)** — finish-time range + evidence grade on branch `r11-7-finish-estimate`; the runner chose to build after the spike recommended against it; the R11.6 decision came later the same day, see above.) Earlier the same day (**R11 built through R11.5; R11.6 and R11.7 spiked** — evidence + `no_data`, past builds, consistency/taper, exclude-from-analysis, race-shoe readiness shipped on branch `r11-race-readiness`; both spikes await the runner's decision, see §R11.) Earlier the same day (**R11 — Race readiness v2 scoped** at the runner's request: evidence + drill-down, past builds at the same week, consistency/taper, activity exclusion, race shoe, then spike-gated fast-finish and finish-time range; nice-to-haves parked with triggers; see §R11.) Earlier the same day (**R10.4 built** — the dashboards also live in the app: Race blocks section + threshold-pace line.) Earlier the same day (**R10.2 backend built** — block comparison, B25; dashboard page 2 reads it after deploy.) Earlier the same day (**R10.3 code built**: DNF race status, B24; Beneva marked DNF after deploy.) Earlier the same day (**R10 — Training dashboard on claude.ai** scoped and scheduled at the runner's request: page 1 Load · Form · Records, R10.3 race data fixes, then page 2 race-block retrospective — which reverses R8.4's "not chosen"; see §R10.) Prior update 2026-10-15 (**R9.1–R9.4 and R9.6 built; R9.5 code built, go-live human steps pending** — the link is not shared until they are done; E20.) Prior update 2026-10-15 (**R9 — Public deals page for the run club + sign out everywhere** scoped at the runner's request, grounded in a code read of the auth middleware, sessions, rate limiters, deals schema/page, PWA config and Caddyfile; security tasks ship before the link is shared; see §R9.) Prior update 2026-10-10 (**Heat analysis run on the 215 archive weather rows — no effect; external weather lookup + heat-adjusted efficiency parked; new §Parked & gated list (confirmed by the runner).** Prior update 2026-10-10: **R5.3 built; R5.4.1 location and R5.4.2 free-half weather built; R5.4.4 runbook added; R5.5.1–R5.5.2 built; R5.5.3 dry run built, apply pending the runner's review.** Prior update 2026-10-10: **R5.3–R5.5 scoped** at the runner's request — §R5.3 "Bought it" with string provenance (B1 holds), §R5.4 location + weather + splits gated on R5.5 questions, §R5.5 phase-1 shoe performance / wear curves / archive tags; injury context parked with notes; not scheduled. Prior update 2026-10-09: **R8 — Training page: records, races & dashboards** scoped at the runner's request — R8.1 records rules, R8.2 best efforts inside longer runs, R8.3 past-races cleanup, R8.4 dashboards placeholder; not scheduled, see §R8. Earlier the same day: R7.1–R7.3 all closed the same day — R7.3 as an honest "unscrapable"; **R7 — Polish & coverage** added and **scheduled** by the runner: R7.1 design cleanup → R7.2 chat confirmation card → R7.3 scraper coverage (Sport Experts). See §R7. Prior update 2026-10-08: **R6 — Daily-use improvements** scoped from a project-state review: docs refresh, retirement forecast → deal radar, my-size deal filter, gated new-run push; and **RA3 — push-to-deploy** scoped in the RA milestone. Neither scheduled; see §R6 and §RA3. Prior update 2026-07-09: **RA — Remote Access & Deployment** added as the next milestone, prioritized ahead of R3 and R4, which are **parked**; RA pulls R5.2 forward and executes it. Plan doc: REMOTE_ACCESS_PLAN (retired). Prior update 2026-07-08: R2.7.1 Training Depth follow-ups.)
**Inputs:** REDESIGN_PLAN Phase-5 backlog, standing wishlist items recorded in `docs/changelog.md`, the ⚠️ verdicts in `docs/design_decisions.md`, `docs/architecture.md` §16, and user feature requests 2026-07-07.
**Framing:** Anton is evolving from a finished redesign into a long-term personal AI platform. This roadmap sequences that evolution.

**Naming note:** "Phase N" already means *redesign* phases in this repo's history (`p1:`…`p5:` commits). Roadmap phases are prefixed **R** (R1–R5) to avoid collision. Suggested commit prefix: `r2:` etc.

**Complexity scale:** **Low** = within one session · **Medium** = 1–3 sessions · **High** = multi-session, deserves its own §-numbered plan doc first.
**Standing rule inherited from the redesign:** backend + tests before UI; suite green + changelog entry per session; the confirmation-gate posture (design_decisions C9) applies to every agent below.

---

## R1 — Immediate Priorities

*Close the loose ends the redesign and today's migration left behind. Everything here is small, and everything after benefits.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R1.1 | **Commit & finish the documentation program** | ✅ **Done 2026-07-06** (documentation-completion session): the suite + `refactoring/` + `CLAUDE.md` + the rename committed as `docs: complete Phase 1 documentation program`; same session added CLAUDE.md §14 (INVARIANTS) and implemented `.claude/skills/` (13 files). Row moved to project_state §3. | Every future AI session boots on these files; uncommitted docs are one `git clean` from gone. | none | Low |
| R1.2 | **Prune the stale reference sections in `docs/changelog.md`** | ✅ **Done 2026-07-06** (docs-reconciliation session): tail replaced with a pointer into `docs/`; the Retailer Status table was relocated to `architecture.md` §10 first; header retitled. Changelog entries above were untouched. | The changelog is the most-read file in the repo; wrong reference material there actively misleads new sessions. | none | Low |
| R1.3 | **Wire the Replacement Deals card on `/shoes/:id`** | ✅ **Done** (the live section shipped in PR #9; size availability added 2026-07-07, R1.3 — see project_state §3 and changelog 2026-07-07). Same-type active deals, worst-discount-first, brand/model/retailer/price/savings/sizes/link, with loading/error/empty/no-type states. | Closes the oldest visible loose end; makes the cross-domain bridge useful exactly where retirement decisions happen. | none (data exists) | Low |
| R1.4 | **Guard the `ShoeRun` proxy traps** | ✅ **Done 2026-07-07** (Session B): `contains_eager(ShoeRun.activity)` added to all five run-list seams; model WARNING comment added; no proxy `.filter()` misuse found. Row → project_state §3. | Today's migration left exactly one loaded gun for future code (N+1 + silently-broken filters). Cheapest possible insurance, best done while fresh. | none | Low |
| R1.5 | **Debt sweep #1** | ✅ **Done 2026-07-07** (Session B, four commits): (a) Task D — `rotation.attach_computed_fields`, router→router import gone; (b) `scraper_manager` shim deleted (5 consumers); (c) pure `app/utils/pace.py` (3 copies collapsed); (d) `chat_service.MODELS` single-sources the catalog + id-based provider routing. Row → project_state §3. | Clears every ⚠ flag in the dependency graph except fat routers; each item is small but they compound into real drift risk if left. | none | Low–Medium (one session, four commits) |
| R1.6 | **Decide APScheduler** | ✅ **Done 2026-07-07** (Session B): removed from `requirements.txt` (default outcome); scheduling note added to `scrapers/lock.py`; E5 → Superseded. Reinstate only with an R4.1 design. Row → project_state §3. | A dependency without an architecture invites drive-by wiring that would collide with the single-process scrape lock. | none | Low |

**All of R1 is complete (2026-07-07). R2.1 then shipped 2026-07-07.** Next in R2: R2.2 schema authority, then R2.7 training depth.

---

## R2 — Core Platform

*Turn "works on my machine, trusted LAN" into a platform that can safely grow interfaces. R2 is the gate in front of R3–R5.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R2.1 | **Security pass** ✅ **Done (2026-07-07)** | Shared bearer token enforced on `/api` and `/mcp` (Claude Desktop's `mcp-remote --header` and `chat_service`'s loopback client both send it); default bind to `127.0.0.1`, `API_HOST=0.0.0.0` the explicit LAN opt-in. **Shipped**: pure-ASGI middleware, fail-fast on missing secret, SPA `VITE_ANTON_SECRET`, 13 HTTP-layer tests (E1 → E7). *Rate limiting on `/api/chat/message` was split out as a separate R2 item* (plan §6) — not part of R2.1. | The acknowledged precondition for *everything* exposure-increasing (agents unattended, mobile, remote MCP). Converts the trust model from network posture to application property. | none — do first in R2 | Medium |
| R2.2 | **Schema authority resolution** – ✅ **Done (2026-07-07, Session E)** | Alembic becomes the sole schema source: `create_all` demoted to test fixtures; `legacy_migrations/` archived; live DB + `.bak*` files relocated out of the tree (e.g. `~/anton-data/`) with a dated-backup convention; `DATABASE_URL` already supports the move. | Ends the "model edit without migration silently diverges" trap and the five-backups-next-to-source ambiguity. Prerequisite hygiene for every future migration. | R1.1 (docs committed) | Medium |
| R2.3 | **Indexed read paths over the canonical table** ✅ **Done (2026-07-08, Session I)** | Shipped: `unified_activities` now issues one indexed SQL query (all filters + newest-first order + LIMIT/OFFSET pushed to the DB) behind the unchanged seam, served by the new composite index `ix_activities_type_run_date` (migration `b8c9d0e1f2a3`); `services/watchlist.py` extracted from the fat router (thin adapter + value-object dataclasses). Suite 127 → 128. See project_state §3 and changelog 2026-07-08. | R1.4 (eager-loading conventions set) | Medium |
| R2.4 | **Shoe-type controlled vocabulary** ✅ **Done (2026-07-08, Session K)** | Shipped: `app/utils/shoe_types.py` owns the vocabulary, served at `GET /api/shoe-types`, validated on the write schemas (422 on off-vocab); the frontend `lib/shoeTypes.js` copy is deleted (reduced to presentation-only colours + a title-case formatter, fetching via `useShoeTypes()`). Migration `c9d0e1f2a3b4` normalized 9 legacy `owned_shoes` free-text values (E4-reconciled). Suite 133 → 141. See project_state §3 and changelog 2026-07-08. | none | Low–Medium |
| R2.5 | **Scrape observability** – ✅ **Done (2026-07-08, Session L)** | Persist scrape runs/attempts (per retailer: started, finished, product count, error) written by the orchestrator; surface per-retailer health + trend in Settings → Sync & Scraping. | "Is Altitude quietly broken?" becomes a query instead of log archaeology. The substrate R4.1 (scheduling) and R4.5 (watchdog) require. Forces the documented decision on the single-process lock. | none | Medium |
| R2.6 | **Server-side conversation & memory persistence** – ✅ **Done (2026-07-08, Session M)** | Move Son of Anton conversations (and checkpoint-prompt state) from localStorage into the backend (tables + endpoints), keeping the client stateless-per-request contract. | Device-bound memory contradicts the API-first multi-client principle; agents (R3) need shared context; quota-trimming currently discards history silently. Scheduled-to-change in design_decisions C8. | R2.1 (chat endpoints stop being anonymous) | Medium |
| R2.7 | **Training & Activity Depth** ✅ **Done (2026-07-08)** | A self-contained milestone adding richer per-activity data, smarter records, athlete-level fitness metrics, and activity editing. Eight sub-items (T1–T8) ordered internally by dependency — schema foundation first, then services, then UI. **All shipped across Sessions F/G/H — see §R2.7 and project_state §3.** | Turns the Training tab from a volume tracker into a genuine training log; makes the records card trustworthy; surfaces COROS athlete metrics the platform already fetches but discards. | R2.2 (migration hygiene before schema changes); internal sub-item dependencies noted in §R2.7 | Medium–High (write TRAINING_DEPTH_PLAN (retired) before executing) |

**Order within R2:** 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7. (Security first; schema hygiene before anything that adds tables — 2.5, 2.6, and 2.7 all add columns/tables and should be born as clean migrations. R2.7 can run in parallel with 2.3–2.6 once 2.2 is done.)

---

## §R2.7 — Training & Activity Depth (detailed breakdown)

*Eight sub-items from user feature requests (2026-07-07). TRAINING_DEPTH_PLAN (retired) is the executing contract — this milestone touches the canonical `Activity` table and the PB algorithm, both of which require the E4 migration discipline.*

**Internal dependency order: T1 → T2 → T3 (schema foundation), then T4/T5/T6 in parallel, then T7, then T8.**

**Progress:** ✅ **Complete — all eight sub-items T1–T8 (Sessions 1–3, F/G/H).** Session 1 (2026-07-07, F): T1 tag vocabulary + 4 `activities` columns (migration `e5f6a7b8c9d0`), T2 COROS field population, T3 PB eligibility fix. Session 2 (2026-07-08, G): T4a month volume axis, T4b date-range picker (backend `date_from`/`date_to` + UI), T5 `athlete_metrics` table + fitness card (migration `f6a7b8c9d0e1`), T6 `/activities/:id` edit + shoe reassignment (INV-1 ledger) + race promotion. Session 3 (2026-07-08, H): T7 `planned_races.activity_id` FK (migration `a7b8c9d0e1f2`, set by the T6 promote flow, deep-links past-race rows) · T8 `suggest_tag_from_name` + `sync_coros_runs` prompt extension (suggestion only, C9). See changelog and project_state §3. **Follow-ups from testing: see §R2.7.1 below (F1–F4) — T2 field population, volume reconciliation, T5 fitness wiring, and the Training-tab 2×2 grid.**

### T1 — Extend the Activity model

**What:** Add nullable columns to `activities` via a reversible Alembic migration:

| Column | Type | Notes |
|---|---|---|
| `activity_tag` | `String(30)` | Controlled vocabulary (see below); nullable — existing rows untagged |
| `best_km_pace_s` | `Integer` | Best consecutive-km pace within the activity (s/km); null if < 1 km |
| `training_load` | `Float` | COROS training load score if available; null otherwise |
| `training_focus` | `String(50)` | Coaching label (e.g. "Aerobic base", "Lactate threshold") — from COROS or manual |

Note: `elapsed_time_s` already exists on the `Activity` model — verify it is being populated by the COROS sync path before T2.

**`activity_tag` controlled vocabulary** (served by the backend — same pattern as R2.4 shoe-type):
`Easy` · `Long Run` · `Recovery` · `Tempo` · `Intervals` · `Track` · `Workout` · `Trail` · `Parkrun` · `Race`

Tag is user-set or inferred from COROS activity name heuristics at sync time (T8). It is the governing input for PB eligibility (T3), race promotion (T6), and the weekly summary agent (R3.1). Treat vocabulary edits as schema-grade changes — the list must not grow casually.

**Migration discipline:** follow E4 (reversible downgrade, named backup, pre/post reconciliation). These are purely additive nullable columns — downgrade simply drops them. Low risk, but the discipline is non-negotiable.

### T2 — COROS sync field population

**What:** Update the COROS confirm-and-log path (`services/coros.py` + `mcp_server.confirm_coros_run`) to populate the fields the COROS API returns but the current sync discards: `name`, `elevation_gain_m`, `moving_time_s`, `elapsed_time_s`, `avg_cadence`, `calories`, `training_load`, `training_focus`.

**Confirmation protocol extension (C9 compliance):** When a COROS field can't be cleanly mapped to Anton's vocabulary (e.g. COROS proprietary training-load scale, or a `training_focus` label that doesn't match Anton's vocabulary), surface the best-guess value in the sync confirmation step alongside the shoe suggestion — *"COROS labels this 'Marathon Pace', mapping to tag `Tempo` — correct?"* The runner confirms or overrides; sync never silently assumes. This extends the existing `sync_coros_runs` MCP prompt's confirmation table.

**Dependency:** T1 (columns must exist before they can be written).

### T3 — Records algorithm fix

**The problem:** The current PB algorithm uses average pace over a whole activity within a distance band. A session of 1 km intervals with full-stop rests between them can match a 5 km race distance at interval pace — producing a false "5k record."

**Recommended approach — tag-based exclusion (primary) + elapsed-time guard (secondary):**

Primary filter — exclude by tag:
- `Intervals` and `Track` → always excluded from PB calculations
- `Race` and `Parkrun` → always included
- `Easy`, `Long Run`, `Recovery`, `Tempo`, `Trail`, `Workout` → included (a slow long run won't break a 5k PB; if a tempo run does, it's legitimate)
- Untagged activities → apply the elapsed-time guard below

Secondary filter — elapsed-time guard for untagged activities:
- If `elapsed_time_s > 1.5 × moving_time_s` → flag as suspicious, exclude from PB, surface a `pbs_excluded_reason` field in the response so the UI can show "N activities excluded — tag them to reconsider"

**Why not elapsed-time-only:** elapsed ≈ moving for both an easy 5k and a race 5k; the ratio only catches stop-heavy sessions. The tag is the clean intentional signal; the ratio is the right fallback for untagged history (including the 8-year Strava archive).

**Implementation:** update `services/strava_stats.py` PB query to join `Activity.activity_tag` and apply the exclusion filters. Add `pbs_excluded_count` and `pbs_excluded_reason` to the PB response for transparency.

**Dependency:** T1 (tag column must exist); T2 (to populate tags on new COROS activities going forward).

### T4 — Training tab display improvements

Two independent UI changes, committable separately. No schema dependency — verify the backend params noted below.

**T4a — Months instead of week numbers:** Replace week-number axis labels on the mileage/volume chart with month labels ("Jun", "Jul"). The underlying data stays weekly — this is a display/axis-formatting change only. No backend change required.

**T4b — Date range selection:** Add a date-range picker to the Training tab header controlling the activities list, volume chart, and summary card. `/api/activities` already accepts `date_from`/`date_to` params. Verify `/api/training/summary` does too — add them if not. Default range: last 90 days (preserving current implicit behaviour). Persist selection in React state only (resets on navigation — intentional).

### T5 — Athlete fitness metrics

**What:** A new table `athlete_metrics` storing periodic COROS athlete-level snapshots — not per-activity, but per-sync:

| Field | Type | Source | Notes |
|---|---|---|---|
| `id` | Integer PK | — | |
| `vo2max` | Float | COROS API | ml/kg/min |
| `threshold_pace_s_per_km` | Integer | COROS API | Lactate threshold pace |
| `race_predictions` | JSON | COROS API | `{"5.0": 1234, "10.0": 2468, ...}` — distance_km → predicted_time_s |
| `captured_at` | DateTime | server | When this snapshot was taken |

A new card on the Training tab (alongside Records and Races) shows the most recent snapshot: VO2 Max, threshold pace formatted as "M:SS/km", and race predictions across standard distances (5k, 10k, HM, marathon). Refreshed on each COROS sync.

**COROS API coverage:** Before planning the sync implementation, verify which COROS Open-API endpoint exposes these fields — include a discovery step in TRAINING_DEPTH_PLAN (retired). If the server-side `coros_client` path cannot access them (credential restriction), extend the `sync_coros_runs` Claude Desktop agent prompt to fetch and confirm them alongside runs.

**Dependency:** T1 (Activity schema stable before adding new tables); T2 (establishes the COROS field-mapping pattern).

### T6 — Activity edit & open

**What:** An activity detail view (slide-over panel or `/activities/:id` page) enabling:
1. View all activity fields (distance, pace, HR, elevation, tag, notes, shoe)
2. Edit: `activity_tag` (dropdown from T1 vocabulary), `name`, `description`/notes, and shoe attribution via a shoe-picker
3. **Promote to race:** when tag is set to `Race`, offer "Add to races" — pre-fills a `PlannedRace` row with the activity's date, distance, and time as the result with status `completed`. This is the workflow for "I ran a race and want it in the races dashboard."

**New service function:** `rotation.reassign_attribution(db, activity_id, new_shoe_id)` — removes the existing `ShoeRun`, decrements the old shoe's mileage counter, increments the new shoe's, creates the new `ShoeRun`. This must flow through the mileage ledger invariant (INV-1), not a raw ORM update.

**New endpoint:** `PATCH /api/activities/{id}` — accepts partial updates to tag, name, description; shoe reassignment goes to a separate sub-endpoint `POST /api/activities/{id}/reassign-shoe` (write semantics differ).

**Dependency:** T1 (tag field must exist); T3 (tag drives PB re-evaluation after an edit changes a tag).

### T7 — Past race → activity link

**What:** Add `activity_id` (nullable FK → `activities.id`) to `planned_races`. When a `PlannedRace` is marked `completed`, link it to the `Activity` that was the race. Past-race rows on the Races card become tappable links opening the T6 activity detail view with full stats. The T6 "promote to race" flow sets this FK automatically.

**Migration:** additive nullable FK column — low-risk, reversible downgrade drops the column.

**Dependency:** T6 (the activity detail view it links to).

### T8 — Activity tag inference from COROS name

**What:** When COROS sync populates `Activity.name` (T2), apply a simple heuristic to *suggest* an `activity_tag` at confirmation time rather than leaving it blank:

| COROS name pattern (case-insensitive) | Suggested tag |
|---|---|
| Contains "interval", "repeat" | `Intervals` |
| Contains "long run", "long" | `Long Run` |
| Contains "tempo", "threshold" | `Tempo` |
| Contains "race", "marathon" | `Race` |
| Contains "parkrun" | `Parkrun` |
| Contains "recovery", "easy", "jog" | `Recovery` or `Easy` |
| Contains "trail" | `Trail` |
| Contains "track" | `Track` |
| No match | untagged — user sets manually |

The suggested tag appears in the COROS sync confirmation table. The runner confirms or overrides — heuristics are never auto-applied silently (C9). Implementation is a pure extension of the `sync_coros_runs` MCP prompt text plus a small helper function; no new backend endpoints.

**Dependency:** T2 (name field populated at sync time); T1 (tag field exists to receive the value).

---

## §R2.7.1 — Training Depth follow-ups (bug-fix pass, pre-R3) ✅ Done — Session Q, 2026-07-08

*Four gaps surfaced by hands-on testing after R2.7 was marked complete (2026-07-08). Small, self-contained; finishes the training milestone honestly before R3. Decisions locked with the runner: rolling-365-day volume window · 2×2 = Races/Records/Fitness/Predictions · dedicated `sync_fitness` prompt + new `running_level` field. Migration `f2a3b4c5d6e7`. Suite 185 → 188.*

**All four items shipped: F1 → F2 → F3 → F4.**

### F1 — Finish COROS + manual run field population (closes T2 for real)

The COROS *write* path (`confirm_coros_run` → `coros.confirm_run` → `rotation.log_run`) already persists all rich fields, but in practice elevation/times/cadence/calories/load/focus land NULL because the `sync_coros_runs` prompt fetches only `querySportRecords` (which doesn't return them) and never calls `getActivityDetail`. `log_run_to_shoe` lacks the rich params entirely.

- Update the `sync_coros_runs` MCP prompt to call the COROS `getActivityDetail(labelId, sportType)` per confirmed run and pass elevation/moving/elapsed/cadence/calories into `confirm_coros_run` (C9-gated, no silent behavior).
- Add the same optional rich params (+ `activity_tag`, validated) to `log_run_to_shoe` and forward to `rotation.log_run` (already supports them).
- Out of scope: the narrow REST manual path (`ShoeRunCreate`/`CorosAssignment`) — flagged as a known parity gap.
- Test: `rotation.log_run` persists the rich fields at the service chokepoint.

### F2 — Reconcile the 12-month volume figures

The "Last 12 mo" stat tile (12 calendar-month buckets, `Math.round`) and the Volume header total (rolling-365-day range, `.toFixed(1)`) disagree by window boundary + rounding. Fix (frontend `Training.jsx` only): compute the tile from a fixed **trailing-365-day** query and unify rounding, so it equals the header total when the `1y` preset is selected. No backend change (`/api/training/summary` already takes `date_from`/`date_to`).

### F3 — Fitness metrics: populate T5 end-to-end + running level

The `athlete_metrics` table, `record_athlete_metrics` tool, `GET /fitness` endpoint, and `FitnessCard` all exist, but nothing orchestrates the COROS fetch, so no snapshot is ever recorded and the card stays hidden.

- Add nullable `running_level` (Float) to `AthleteMetric` (reversible E4 migration off `a7b8c9d0e1f2`); thread it through `services/fitness`, `FitnessResponse`, and `record_athlete_metrics`.
- New `sync_fitness` MCP prompt (sibling of `sync_coros_runs`): calls COROS `queryFitnessAssessmentOverview`, confirms with the runner (C9), then `record_athlete_metrics` (VO2max, threshold pace, race predictions, running level).
- Test: `running_level` round-trips through service + endpoint; empty envelope still `has_data=False`.

### F4 — Training tab 2×2 card grid

Replace the full-width vertical stack of Fitness/Races/Records with a `grid grid-cols-1 gap-4 lg:grid-cols-2` of four cards: **Races · Records · Fitness · Predictions**. Extract race predictions out of `FitnessCard` into a new `PredictionsCard`; wrap the inline Records grid in a new `RecordsCard` using the standard outer-card shell. The stat strip + Volume chart stay full-width above; the Activities list stays full-width below. Cards stack to one column on mobile.

**Dependency:** F4's PredictionsCard/Fitness split pairs with F3's card content, but the layout work is otherwise independent.

---

## RA — Remote Access & Deployment *(added 2026-07-09 — executes before R3/R4)*

*Turn "reachable on my laptop at home" into "reachable from Claude mobile anywhere." RA pulls **R5.2** forward and executes it. Phase 1 (RA1) is backend-only — the DB + MCP on an always-on host so `sync_coros_runs` works from a phone on cellular; remote/mobile *clients* are RA2 and later R5.1. **REMOTE_ACCESS_PLAN (retired) is the executing contract** — threat-model shift, hosting decision D0, spikes S1–S3, sequencing, cutover runbook, and the invariants checklist all live there; this table is the index.*

*Two facts shape RA1 (plan §2): Claude mobile connectors are called from **Anthropic's cloud**, so the MCP endpoint must be publicly resolvable over HTTPS — a Tailscale-into-the-LAN overlay does not satisfy the goal; and the laptop sleeps, so serving moves to an always-on host (cloud VM recommended, always-on home box the fallback — decision gate D0). A1 (local-first) is amended, not abandoned: local-first stays the dev posture; serving becomes hosted single-tenant.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| RA1.0 | **Hosting decision (D0) + discovery spikes (S1–S3)** ✅ **Done (2026-07-09)** | S1: connector requires OAuth or capability-URL (bearer not supported — #112/#411 closed); S2: mobile prompt invocability unconfirmed, C6 fallback documented; S3: existing ASGI middleware sufficient, full OAuth deferred. D0: Option A cloud VM (Hetzner/Fly.io ~$5–8 CAD/mo; always-on home box = escape hatch for DC-IP scrape degradation). Findings in REMOTE_ACCESS_PLAN (retired) §4–§5; A1 amended in design_decisions.md. | Every subsequent item's design branches on these answers; doing them first is the difference between a plan and a rewrite. | none | Low (research) |
| RA1.1 | **Auth v2 — per-client, connector-compatible tokens** ✅ **Done (2026-07-09)** | Named `ANTON_TOKENS="name:token,..."` map (desktop/loopback/spa); capability-URL bypass at `/mcp/<CONNECTOR_TOKEN>/...` (path-rewritten in ASGI middleware); constant-time multi-token OR comparison; `get_named_token("loopback")` for chat_service; `ANTON_SECRET` rotated. `test_auth.py` rewritten +8 tests; `test_http_smoke.py` updated for shared env setup. Suite 188 → 196. E7 → Superseded by E9. | E7's shared cleartext token was designed for a trusted LAN; the internet threat model (plan §3) requires TLS-only transport, revocation per client, and visible failures. The mobile connector literally cannot connect until this exists. | RA1.0 | Medium (High if OAuth path) |
| RA1.1b | **OAuth 2.1 upgrade for the connector (pre-public gate)** ✅ **Done (2026-07-09)** | **Path 1 chosen** — `mcp[cli]` 1.28 has `OAuthAuthorizationServerProvider` Protocol + `create_auth_routes()` (4 endpoints). Built: `AntonOAuthProvider` (9 async methods), `oauth_auth_codes` + `oauth_tokens` tables (migration `0b1c2d3e4f5a`), `GET/POST /oauth/login` page, middleware OAuth fallback. Capability-URL **deleted** (never went public). 18 new tests; suite 194 → 210. E9 updated; capability-URL → Superseded. | The URL-as-credential leaks into every log line, and the connector is the primary long-term consumer — build its real auth once if the SDK makes it contained. | RA1.1; **decide before RA1.5** | Medium–High (OAuth) / Low (keep fallback + redaction) |
| RA1.2 | **Deployment substrate** ✅ **Done (2026-07-09)** | `backend/Dockerfile` (Python 3.11-slim + `playwright install --with-deps chromium` + `TZ=America/Toronto` + `--workers 1`); `backend/.dockerignore`; `docker-compose.yml` (loopback-only port + `~/anton-data` volume + healthcheck); `deploy/Caddyfile` (Let's Encrypt TLS + `flush_interval -1` unbuffered streaming + credential-redacting log filter); `deploy/.env.production.example`; **INV-9** added to CLAUDE.md §14. Remaining acceptance (deployed HTTPS + streaming verified through proxy) = human steps at RA1.5. | The always-on host is the whole point of phase 1; the one-worker pin keeps two load-bearing in-process invariants true by construction rather than by luck. | RA1.0 | Medium |
| RA1.3 | **Surface & abuse hardening** ✅ **Done (2026-07-09)** | `AccessLogMiddleware` (structured per-request log + credential redaction); per-IP auth-failure rate limiter (429 after burst; `AUTH_FAILURE_LIMIT_PER_MINUTE` env); 401 logged at WARNING with source IP; login-page rate limiter (`LOGIN_FAILURE_LIMIT_PER_MINUTE` env); Caddyfile comment updated. Suite 210 → 231. Remaining human step: uptime pinger on `/health` (execute at RA1.5). | An internet-facing service gets scanned within minutes of DNS propagating; the goal is that hostile traffic is slow and visible, not invisible. | RA1.2 | Low–Medium |
| RA1.4 | **Backups off-laptop** ✅ **Code done (2026-07-09); restore drill = human step** | Litestream config (`backend/litestream.yml`; B2/S3-compatible; 14-day WAL retention + daily snapshots); `backend/entrypoint.sh` (restore-on-start + replicate-while-running; plain uvicorn without `LITESTREAM_BUCKET`); Dockerfile installs Litestream v0.3.13 + sqlite3 CLI + switches CMD; `deploy/restore.sh` (drill + disaster recovery); `deploy/pull-snapshot.sh` (laptop dev-DB seed). Human steps at RA1.5: provision B2 bucket + set vars; run `deploy/restore.sh` to scratch path + verify counts; pull snapshot; uptime pinger. | The recovery story today is file copies on a laptop that will no longer hold the live DB. A backup that has never been restored is a hope. | RA1.2 | Low–Medium |
| RA1.5 | **Cutover & validation** – ✅ **Done (2026-08-29)** | Execute the plan §7 runbook: E4-style count reconciliation across the DB move, re-point Claude Desktop, add the claude.ai connector. Two exit criteria: (1) **end-to-end mobile sync on cellular** — COROS fetch → suggest → confirm → run lands with rich fields and mileage updates; (2) **the DC-IP scrape checkpoint** — full scrape from the new host compared per-retailer against the home baseline via R2.5 `scrape_runs`; material degradation invokes the home-box escape hatch (no paid-bypass escalation, D3 stands). **Both closed 2026-08-29.** Criterion (2): every enabled retailer within normal week-to-week noise, JD Sports Canada (the canonical bot-flag risk) flat at 39 products, zero warning/error health states — Option A (Hetzner) confirmed, home-box escape hatch not invoked. Criterion (1): validated live from the phone, off WiFi, via the claude.ai connector — run landed with rich fields and mileage updated. Getting here required fixing three real bugs in the connector's OAuth chain (missing RFC 9728 protected-resource metadata; RA1.1c public-PKCE client; an HTTPS→HTTP downgrade-redirect from Uvicorn not trusting Caddy's forwarded headers) — see changelog 2026-08-12/2026-08-29. **Remaining before RA1 as a whole is fully done (not blocking, one-off infra):** the RA1.4 restore drill and the RA1.3 uptime pinger on `/health`, neither yet executed. | The milestone's definition of done is the user story itself, plus proof the deals domain didn't quietly pay for it. | RA1.1–RA1.4 | Medium |
| RA1.6 | **Docs reconciliation** – ✅ **Done (2026-08-29)** | `architecture.md` §11 rewritten for the internet trust model (three-credential-type model, RFC 9728, the Caddy split, the proxy-headers fix); `CLAUDE_DESKTOP_SETUP.md` rewritten (Desktop bearer-token + claude.ai OAuth connector setup, with the three known-fixed failure modes documented); design_decisions.md: A1 confirmed executed (not just amended — the VM is live, both RA1.5 exit criteria closed); E7 → per-client tokens was already superseded by E9/E10, confirmed current; **R5.2 formally closed** in the Superseded table — retired as a distinct roadmap question, its content now lives in the RA milestone; `CLAUDE.md` INV-9 confirmed present (Dockerfile CMD + docker-compose.yml pin, documented in §14). | A fresh session reading `docs/` must describe the deployed reality, not the laptop. | RA1.5 | Low |
| RA2 | **Remote clients** – ✅ **Done — RA2.1 (2026-08) + RA2.2 PWA (shipped; mobile UI pass 2026-09-04)** | **RA2.1 (remote SPA + session auth) ✅ done** (see §11 auth model + design_decisions E10). **RA2.2 (PWA pass) — scoped & chosen as the next build:** installable service-worker PWA over the already-remote SPA — home-screen icon, standalone launch, app-shell + offline **read** (cache-last-loaded so it opens usefully with no signal), refresh-on-reconnect. **Writes deliberately require connectivity** (graceful "you're offline" state, NOT a queued write-replay): an offline write-queue would replay confirmation-gated mutations (C9) against stale state and break the mileage ledger (INV-1) / single-writer (INV-9) — double-counted mileage, orphaned runs, silent conflicts. Offline write-queue is split out as a separate gated R5.x item, built only on a felt "I needed to log off-grid and couldn't" need (and note: the main log path is COROS-sync, which is connector-mediated and un-queueable anyway — C6). Own plan doc: RA2_2_PWA_PLAN (retired). **R5.1 native remains gated behind RA2.2** — the PWA is the honest test of whether native is even needed (push, the main native-only win, was retired with R3.5). **Known follow-up — ✅ resolved 2026-09-04 (bug batch v3 #3):** the offline-detection probe sent `HEAD /health`, which returned 405 (the route only accepted GET) — so the "offline — showing last synced data" ribbon showed even when online. Fixed both sides as planned: (A) frontend probes with `fetch('/health', {method:'GET', cache:'no-store'})` and treats *any* resolved HTTP response (even non-2xx) as "online" (only a network throw → offline); (B) `/health` now accepts HEAD too (`methods=['GET','HEAD']`). See changelog 2026-09-04. Still open: the `.webmanifest` content-type header is absent (Caddy has no MIME mapping for the extension) — harmless (browsers parse the linked manifest by content), optional Caddyfile cleanup. | The stepping stones from "backend reachable" to "the app in my pocket," each useful on its own; the PWA delivers ~90% of the pocket-app feel for a fraction of native's cost. | RA1 ✅; RA2.1 ✅; precedes R5.1 | RA2.2 Medium (own plan doc) |
| RA3 | **Push-to-deploy (CI/CD to Hetzner)** – 📋 **scoped 2026-10-08, not scheduled** — CI half exists (E15); the deploy-to-Hetzner job is not built (felt-need) | A push to `main` on GitHub runs the tests and the frontend build in GitHub Actions; if they pass, Actions SSHes into the Hetzner host with a dedicated deploy key and runs a committed `deploy/deploy.sh`: pre-deploy SQLite snapshot → `git pull --ff-only` → `docker compose up -d --build` → wait for healthy → rsync the CI-built `dist/` to `/var/www/anton` → public `/health` check. Replaces the manual pull/rebuild and the laptop-side `npm run build` + rsync. The production `.env` stays on the server and is never seen by CI. Full scope, decisions and exit criteria in **§RA3** below. | Manual deploys are two separate procedures (backend on the server, UI from the laptop) that are easy to forget between sessions — and they have been forgotten (2026-10-07). Gating deploys on the suite makes "main is green" and "production matches main" the same fact. | RA1.2 (container substrate), RA1.4 (Litestream — the rollback net), RA2.1 (Caddy split / `/var/www/anton`) | Low–Medium (one session + human key/secret setup) |

**Order within RA:** 1.0 → 1.1 → (1.1b ∥ 1.2) → 1.3 + 1.4 → 1.5 → 1.6, with **1.1b decided before 1.5** — the connector's public auth mechanism must be settled before the endpoint exists in public DNS. **Auth v2 and TLS land together or not at all** — a public bind with a single shared cleartext token is a regression, not an intermediate state. RA2 is not scheduled; it waits for RA1 to prove the substrate.

### §RA3 — Push-to-deploy (detailed scope) *(scoped 2026-10-08; execute on a felt need, as with every RA item)*

**Goal:** `git push origin main` is the whole deploy. No SSH session, no laptop build, no rsync by hand. The manual path stays documented and working as the fallback.

**Shape (v1 — build on the server, no image registry):**

```
push to main ─▶ GitHub Actions
                 ├─ test:   backend pytest (Python 3.11, requirements.txt) · frontend npm ci + npm run build
                 │          + the RA2.1 secret grep on dist/ (no bearer / VITE_ANTON_SECRET in the bundle)
                 └─ deploy: (needs test; concurrency group "deploy", cancel-in-progress: false)
                      ssh deploy@host deploy/deploy.sh <sha>
                        1. pre-deploy snapshot: docker compose exec anton sqlite3 /data/shoe_deals.db ".backup /data/backups/pre-<sha>.db" (keep last 5)
                        2. git pull --ff-only (refuse, don't clobber, if the server tree has drifted)
                        3. docker compose up -d --build → wait for the compose healthcheck to report healthy
                      rsync dist/ (CI artifact) → /var/www/anton/   ← backend first, so new UI never meets an old API
                      curl -fsS https://anton.musasouled.com/health → job fails red if not 200
```

**Work items:**
- **D1 `.github/workflows/deploy.yml`** — the two jobs above. `concurrency` serialises deploys (two overlapping `up --build` runs would race the single container — INV-9 is about one writer; don't let CI create two). Frontend `dist/` passed from the test job as an artifact so what was tested is what ships.
- **D2 `deploy/deploy.sh`** — server-side, committed, idempotent; takes the SHA, logs each step, exits non-zero on any failure. Header comment = the rollback runbook (below). Pin the snapshot dir inside the `/data` volume (`~/anton-data/backups/` on the host) — outside the repo, inside what Litestream doesn't replicate.
- **D3 Deploy credential (human step)** — new ed25519 key used *only* by CI; public half in the server's `authorized_keys`, private half as a GitHub secret. Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` (pin the host key — no `StrictHostKeyChecking=no`). Separate from the laptop key, so revoking CI never locks out the runner.
- ~~**D4 CI test environment**~~ ✅ **Answered 2026-10-09 (E15)** — `.github/workflows/ci.yml` runs the suite on a clean `ubuntu-latest` runner, Python 3.11, no browser install (no test needs one) and no network, and runs `vite build`. One fix was needed: OAuth env set in `tests/conftest.py`, because the suite depended on test order and a local `.env`. D1 can reuse these jobs as its test stage rather than defining its own.
- **D5 Docs** — `architecture.md` deployment section, a deploy/rollback runbook, changelog. Also fix the known doc bug: `CLAUDE_DESKTOP_SETUP.md` says `docker compose restart` after editing `backend/.env` — `restart` does not re-read `env_file`; the correct command is `docker compose up -d --force-recreate`.

**Decisions to make at execution time:**
1. **Deploy user.** A dedicated `deploy` user is cleaner than `root`, but membership of the `docker` group is root-equivalent anyway — the honest gain is auditability and a separate revocable key, not containment. Needs write access to the repo checkout and `/var/www/anton`.
2. **Migrations on auto-deploy.** Startup runs `alembic upgrade head`, so any merged migration hits the live DB unattended. v1 answer: the pre-deploy snapshot + Litestream make every deploy reversible, and migrations stay additive (as R5.7's was). Revisit — e.g. a "migration present → require a manual approval" GitHub environment gate — only if a destructive migration is ever planned.
3. **"main is always deployable."** Feature branches (`r5.7-…`, `ra2.2-…`) already merge into main; with RA3, merging *is* shipping. Work-in-progress stays on branches.

**Rollback runbook (goes in `deploy/deploy.sh`'s header):** code-only bad deploy → revert the commit on main and push (CI redeploys). Bad deploy that ran a migration → stop the container, restore `/data/backups/pre-<sha>.db` over `/data/shoe_deals.db`, check out the previous SHA, `docker compose up -d --build`. Litestream point-in-time restore (`deploy/restore.sh`) is the last resort.

**Not in scope (deferred until felt):** building images in CI and pulling from GHCR (revisit if the on-server Playwright build becomes slow or memory-tight on the VM); automatic rollback; preview/staging environments; deploy notifications beyond GitHub's built-in failure email; managing `.env` from CI (secrets stay on the host by design — env edits remain `nano backend/.env` + `docker compose up -d --force-recreate`).

**Exit criteria:** (1) a trivial commit to main reaches production with no manual step, UI and backend both; (2) a deliberately failing test blocks the deploy; (3) a deploy that leaves `/health` failing turns the run red; (4) a pre-deploy snapshot file exists for the deploy; (5) the manual path still works.

---

## R3 — AI Capabilities *(R3.1–R3.4 + R3.6 ✅ shipped 2026-07-10; R3.5 deferred → R6.4, see §Parked & gated)*

*The redesign built the surfaces; R3 populates them. Every agent obeys C9: prepare and propose, the runner disposes. **Parked in favor of RA:** remote reachability is worth more right now than proactive agents — and R3 agents built after RA1 inherit the remote substrate (an agent digest readable from a phone anywhere beats one readable only at home).*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R3.1 | **Weekly Rotation Summary Agent** ✅ **Done (2026-07-10)** | Shipped: `services/weekly_summary.py` compiles the ISO-week digest (volume vs last week, per-shoe usage + shoe_type, retirement pipeline, notable runs tagged Race/Parkrun/Intervals/Tempo/Long Run/Track, 100km checkpoints, next race). `get_weekly_summary` MCP tool + `weekly_rotation_summary` MCP prompt (read-only sibling of `sync_coros_runs`). 20 new tests. Suite 231 → 253. | The first *proactive* value from the AI layer, built almost entirely from existing tools (`get_training_summary`, `retirement_pipeline`, `get_shoe_runs`). Proves the agent pattern cheaply. R2.7 T1 activity tags make "notable runs" (`Race`, `Tempo`) identifiable. | none hard; R2.6 makes digests persistent; R2.7 T1 enriches "notable runs" | Medium |
| R3.2 | **Deal Alert Agent** ✅ **Done (2026-07-10)** | Shipped: `services/deal_alerts.py` — three alert types (new deals sorted by savings %, price drops sorted by drop amount, replacement alerts for ≥ 75% pipeline shoes via shoe_type heuristic); injectable clock for tests. `get_deal_alerts` MCP tool reads `last_deal_alert_check_at` from `AppSettings`, calls the service, advances the high-water mark. `deal_alert_digest` MCP prompt drives the structured briefing workflow. 22 new tests. Suite 251 → 275. Push delivery deferred to R4.2 as planned. | The deals domain's whole purpose is timely opportunity — today it requires opening the app. Backlog item; Home top-deals module is its surface. | R2.5 helps (event source); delivery beyond in-app needs R3.5 | Medium |
| R3.3 | **Shoe review pipeline maturation** ✅ **Done (2026-07-10)** | Shipped: `review_draft` column on `owned_shoes` (migration `a2b3c4d5e6f7`); `rotation.store_shoe_review()` service; `PATCH /api/owned-shoes/{id}/review` REST endpoint + `review_draft` in `OwnedShoeResponse`; `draft_shoe_review` auto-saves after sampling; `save_shoe_review` MCP tool for runner-edited saves; `retire_shoe` nudges the review workflow when notes exist; `shoes://review/{id}` MCP resource. 7 new tests. Suite 275 → 282. | The notes journal exists to feed this; retirement is its natural trigger; it's the payoff of the mileage-anchored journaling discipline. | R1.3 pattern (detail-page work); storage column | Low–Medium |
| R3.4 | **MCP watchlist parity + resource expansion** ✅ **Done (2026-07-10)** | Shipped: `get_watchlist` MCP tool (thin adapter over `watchlist_svc.build_watchlist`; on-sale first, watching A-Z; best_deal, best_ever_price, last_seen per retailer); `deals://watchlist` resource; `training://summary` resource (last 12 weeks weekly); `training://fitness` resource (latest AthleteMetric snapshot). Suite stable at 251. One `r3:` commit. | Son of Anton currently can't answer "what am I watching and what's the best price ever?" — the only major read surface missing from the AI layer. | R2.3; R2.7 T5 for fitness resource | Low |
| R3.5 | **Notification channel (Email MCP or equivalent)** *(⏸ deferred 2026-07-10 — see note below; **revisit scoped as R6.4, 2026-10-08** — Web Push to the installed PWA, gated on measured inbox latency)* | One outbound channel for agent output — a digest endpoint/resource the phone reads, or true push (email) if pull proves insufficient. Decide once, use for R4.2/R4.3/R4.5. | Agents that can only speak when spoken to aren't agents. Channel choice is a one-time decision every proactive feature reuses. | R2.1 (an authenticated system shouldn't email from an open one) | Medium |
| R3.6 | **Race-block training advisor** ✅ **Done (2026-07-10)** | `services/race_advisor.py` (`race_block_context` — soonest upcoming race, last 12 weeks weekly volume + avg, retirement pipeline with shoe_type, latest fitness snapshot); `get_race_block_context` MCP tool (weeks_back param, 1–52 clamped); `race_block_advisor` MCP prompt (four-section advisory: race countdown, volume trend keyed to training phase, rotation concerns, fitness/pace comparison). Advisory only — no plan generation; no confirmation gate; no schema changes. 14 tests. Suite 282 → 298. | Highest-value reasoning use of data already collected; zero new schema. The runner's actual use case (sub-2:37 target). R2.7 T5 makes this considerably richer. | R3.1 (shares digest machinery); R2.7 T5 (fitness metrics) | Medium |

**Order within R3:** 3.1 → 3.4 → 3.3 → 3.2 → 3.5 → 3.6. **R3.1–R3.4 + R3.6 shipped 2026-07-10; R3.5 deferred (see below).**

**R5.7 note (2026-10-07):** the COROS direct sync deliberately ships *without* a "new run waiting" push — that is the first concrete thing that would want R3.5's channel, and the natural trigger to revisit it (a push of "1 new run to confirm" with a deep link to `/new-runs`). Not built; still a gated decision.

**R3.5 deferral note (2026-07-10):** R3.1/R3.2 already ship pull-based access to agent output — `get_weekly_summary` and `get_deal_alerts` are live MCP tools, invocable on demand from Claude Desktop or mobile today. What R3.5 would add on top is *unprompted* delivery, and that's only worth designing once something is actually trying to push — right now there's no scheduled process generating output nobody sees. Building the channel ahead of that need means guessing at requirements (email vs. digest endpoint, trigger conditions, noise tolerance) with no real usage to inform the guess — the same over-building C10 and A5 both declined elsewhere in this project (`design_decisions.md`: C10 rejected normalizing the chat schema as "speculative infra" at single-user scale; A5 names "a second consumer exists" as the trigger for a typed API contract rather than building one ahead of need). **Revisit trigger:** when R4.2, R4.3, or R4.5 is reached and the lack of a channel is a felt problem ("this fired and I never saw it"), not before. R4.1 (scheduled scraping) has no dependency on R3.5 and is the natural next move — it will surface whether unattended output actually needs pushing, which is a better design input than reasoning about it now.

---

## R4 — Automation *(closed: shipped items marked ✅; R4.2/R4.3 declined 2026-08-29 — see §Parked & gated)*

*Remove the human trigger where — and only where — the human isn't the point. Confirmation gates on writes remain non-negotiable. **Parked with R3:** additionally, R4.1's scheduled scraping is better designed once RA1 has settled where the process actually runs (an always-on host makes scheduling more natural, and the DC-IP scrape validation in RA1.5 informs it).*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R4.1 | **Scheduled scraping** ✅ **Done (2026-07-10)** | Shipped: `services/schedule.py` — `AsyncIOScheduler` with `CronTrigger` (default 3am America/Toronto); opt-in via `SCRAPE_SCHEDULE_ENABLED=true`; `SCRAPE_SCHEDULE_CRON` for override. Wired in `main.py` lifespan. In-memory scrape lock deliberately kept (APScheduler `max_instances=1` + the existing `threading.Lock` = at most one scrape at a time; D4 resolved). `ScrapeRun.trigger="scheduled"` for history. `GET /api/admin/schedule` exposes status + last 5 scheduled runs. SettingsSync "Scheduled Scraping" card (React Query poll 60s). 9 tests; suite 298 → 307. APScheduler 3.x (not 4.x — different API) re-admitted (R1.6). **UI-configurable since #7 (2026-09-04):** the schedule now reads DB → env → default (AppSettings keys `scrape_schedule_enabled`/`scrape_schedule_cron`); `PUT /api/admin/schedule` persists + reschedules the live job at runtime (no restart, safe under INV-9); the Settings card became an editor (enable toggle + time picker + advanced cron); env vars remain the fallback. See design_decisions E12. | Deal data is only as good as its freshness; manual triggering is the platform's biggest remaining chore. | R2.5 (observability) ✅, R1.6 decision ✅; R2.1 before exposing any trigger surface ✅ | Medium–High |
| R4.4 | **Coupon Hunting Agent** ✅ **Done (2026-07-10)** | `get_promo_page_urls` hook on `BaseScraper` (multi-page, subclass-overridable); `services/coupon_hunter.py` read model (`get_stacking_opportunities` — retailers with both active codes AND active deals); `get_coupon_opportunities` + `hunt_coupons` MCP tools + `coupon_digest` prompt. 8 tests. Suite 307 → 313. | Stacking a promo on a qualified deal is real money; currently ad-hoc. | R4.1 (scheduler), scraper heuristics | Medium |
| R4.2 | **Agent scheduling & event delivery** – ⏸ **declined 2026-08-29 (absorbed by the mobile connector)** | Re-scoped pull-only after R3.5's retirement, then declined: with push gone, the remainder was a "deals from the last scheduled scrape" read — but "any new deals?" on mobile already answers this against fresh nightly-scraped data (R4.1), so the added view is a nicety on a surface that already works. R3.1/R3.2 (`get_weekly_summary`, `get_deal_alerts`) + R4.1 + the connector already deliver R4.2's intent. **Revisit trigger:** a felt "I keep re-asking the same deals question and want it scoped to the last scrape" need. | R3's on-demand agents are already "one question away on mobile" — the ambient-delivery gap closed with the connector, not with new code. | R3.1 ✅, R3.2 ✅, R4.1 ✅; connector obsoletes the rest | Low (declined) |
| R4.3 | **Semi-automated COROS cadence** – ⏸ **declined 2026-08-29 (absorbed by the mobile connector)** | Re-scoped pull-only after R3.5's retirement (see history below), then declined on review: the only thing it adds over "just ask Claude" is an *unprompted* time-based reminder — and it can't even be a good one, because Anton's backend can't see the pending count (it lives in COROS; C6), so the nudge would be a mildly-stale timestamp that still sends the runner to the connector to actually sync. The runner already asks on mobile/desktop for a full COROS-vs-logged comparison whenever they think to, and confirmed that's sufficient. Building the nudge would be solving a non-problem (same speculative-infra judgment as C11/A5). **Revisit trigger:** only if forgetting to sync becomes a *felt, recurring* data-freshness gap. *Prior re-scope (kept for history):* Anton contributes a time-based nudge from `last_coros_sync_at` (already on `ActivityStrip`); the real count is agent-side via a check-only `sync_coros_runs` mode. | Sync friction is the main data-freshness gap on the training side — but the connector already lets the runner resolve it on demand. | C6; connector obsoletes the nudge | Low–Medium (declined) |
| R4.5 | **Scraper watchdog** ✅ **Done (2026-07-10, absorbed into R4.2 — Scrape Reliability)** | `_derive_watchdog_alert` in `scrape_history.py` (3-run consecutive error/warning streak); `watchdog_alert`/`watchdog_reason` on every retailer entry; `retailers_needing_attention` top-level field in `scrape_health`. Sidestepped R3.5 dependency by surfacing alerts via the existing `scrape_health` MCP tool (pull-based, not push). Also added: `_fetch_with_requests` retry (3 attempts, 2 s backoff). 10 new tests. Suite 313 → 323. | Silent scraper death is the current failure mode (visible only in logs); the deal feed degrades invisibly. | R2.5 ✅, R4.1 ✅ (R3.5 sidestepped) | Low |
| R4.6 | **New-Retailer Onboarding Agent** ✅ **Done (2026-07-14, from MAINTENANCE_PLAN (retired) I1)** | Shipped: `services/onboarding.py` — `retailers_needing_onboarding` (active retailers with no working scraper, not marked unscrapable — bespoke/shopify/algolia-with-creds excluded), `probe_retailer` (read-only platform sniff + dry-run against a candidate scraper built from the *proposed* config on a transient Retailer, never persisting), `apply_onboarding` (single write path — wires shopify/algolia + enables scraping), `mark_unscrapable` (records the Sporting Life verdict on the row). MCP: `get_onboarding_queue` / `probe_retailer` / `onboard_retailer` (confirm-gated) / `mark_retailer_unscrapable` (confirm-gated) tools + `retailer_onboarding` prompt. REST parity: `GET /retailers/onboarding/queue`, `POST /retailers/{id}/probe|onboard|mark-unscrapable`. `scrape_health` now carries `needs_onboarding` so the R4.5 watchdog and this share one health view. 21 tests. Suite 374 → 395. | A new retailer today is dead weight until a human hand-builds a scraper; this reuses `platform_detection.py` + the dry-run + `scrape_health` to make onboarding a guided, confirmation-gated flow. | R2.5 ✅ (`scrape_runs` health), platform_detection ✅, dry-run endpoint ✅ | Medium |

**Order within R4:** 4.1 → 4.4 → 4.5 → 4.2 → 4.3. **Reordered 2026-07-10:** 4.1 and 4.4 need nothing from R3.5 and lead; R4.5 shipped alongside (watchdog via scrape_health MCP, no R3.5 needed); roadmap R4.2/R4.3 remain blocked on R3.5.

---

## R5 — Long-Term Vision

*Anton as a durable personal platform: reachable anywhere, ingesting everything relevant, reasoning across a decade of data. Everything here deserves its own plan doc before code.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R5.1 | **Native mobile client** – ⏸ **parked; PWA-tightening chosen instead (2026-09-04)** | The long-anticipated app: Home as launch screen (built to budget for this), log-run + sync-nudge + deal alerts as the core loop. Precede with a typed/generated API contract (OpenAPI client) — the moment a second consumer exists, hand-matched string contracts stop scaling (design_decisions A5's named trigger). **2026-09-04 resolution:** real phone use of the RA2.2 PWA surfaced four layout bugs (header unreachable on full-bleed chat; no mobile chat layout; Deals filter deck pushing shoes below the fold; FAB overlap) — **all CSS/layout, none native-only** — so the decision resolves toward *tighten the PWA*, not *go native*. Fixed in the RA2.2 (R5.1) mobile UI pass (`ra2:` commits; see changelog 2026-09-04). Native stays parked: the one genuine native-only capability if it's ever revisited is **HealthKit / on-device COROS read** (the C6 unblock — reading COROS/health data without the connector round-trip); push, the other classic native win, was already retired with R3.5. Revisit only on a felt native-only need. | The platform's stated destination; every API-first discipline since Phase 1 was bought for this. | R2.1 (hard gate), R2.6, R3.5; contract-generation spike | High |
| R5.2 | **Remote access story** | **→ Pulled forward (2026-07-09): executed by RA1** — see REMOTE_ACCESS_PLAN (retired). The original question (private overlay vs hosted) is answered there with a decisive fact: Claude connectors call from Anthropic's cloud, so a public HTTPS endpoint is required, and an overlay alone can't deliver the mobile-sync goal. The remote-MCP-for-ChatGPT transport remains deferred; revisit after RA1. | Mobile off-WiFi and any third-party MCP client both need this answered; it's a security-architecture decision, not a feature. | R2.1, R2.2 → superseded by RA1 | (absorbed into RA1) |
| R5.3 | **Purchase-loop closure** – ✅ **Done 2026-10-10**, detail in §R5.3 | Optional provenance from deal → owned shoe: "I bought this" on a deal creates/links an owned shoe with purchase price pre-filled. Must respect B1 (wanting ≠ owning): an *optional recorded event*, never a forced workflow or FK entanglement. | Closes the platform's narrative loop (watch → buy → run → retire → replace) and feeds real cost/km from day one. | R2.4 (shared vocabulary) | Medium |
| R5.4 | **Richer ingestion** – 🟢 **Partial 2026-10-10:** R5.4.1 ✅, R5.4.2 free half ✅, R5.4.4 runbook ✅; **R5.4.3 splits ✅ built 2026-10-20 (B28)**; the external weather lookup stays gated. Detail in §R5.4 | Candidates, each its own decision: per-run FIT-file detail (COROS MCP already exposes FIT downloads) for splits/HR curves; periodic Strava re-exports folded in via the existing idempotent importer; weather-at-run enrichment. Gate each on a question it answers, not on data availability. R2.7 T1 columns provide natural landing spots for split data. | The canonical `activities` table is deliberately a superset schema — it can absorb richer data without restructuring. | R2.3; per-source spikes | High (aggregate) |
| R5.5 | **Longitudinal analytics** – 🟢 **Phase 1 built 2026-10-10:** R5.5.1–R5.5.2 ✅, R5.5.3 dry run built, apply pending the runner's review. Detail in §R5.5 | The decade-scale questions: shoe-model performance correlations (pace/HR by shoe across years), wear-rate curves by type, injury-pattern context (the recurring left-leg history) annotated against volume spikes. R2.7 activity tags make this richer ("race pace trend over 3 years", "interval-session frequency vs PB trajectory"). Read-only analytics over `activities` — no new writes. | This is why eight years of history was imported and made canonical: Anton's endgame is *insight*, not logging. | R2.3, R2.7 T1, R5.4 helps | High |
| R5.6 | **Documentation as infrastructure, permanently** – ♾ **ongoing practice, not a task** | The Phase-2 (implementation) workflow from documentation_creation (retired): milestone plans executed by cheaper coding agents, with `project_state.md` / `roadmap.md` / `design_decisions.md` updated continuously as living artifacts. | The meta-bet of this whole program: sessions that start with accurate context outperform sessions that start with archaeology. | R1.1 | Ongoing |
| R5.7 | **COROS direct sync (backend as MCP client)** ✅ **Done (2026-10-07; plan: COROS Direct Sync, 2026-10-02)** | The backend is a direct OAuth client of the self-service COROS MCP server (no LLM in the data path): `coros_connection` (DCR + PKCE, encrypted rotating tokens) → `coros_mcp_client` (prose parser + contract tests) → scheduled `coros_poller` → `pending_coros_runs` inbox with a deterministic shoe suggestion → "New runs" UI (confirm/dismiss via the single writer) + Settings connection card; Anton MCP tools realigned to the shared queue. Poller and inbox are non-writers (INV-1/INV-9); every run is still runner-confirmed (C9). Decision: design_decisions C11; spike: the coros_mcp_client spike report (retired). Suite 441 → 556. **Deferred under this banner (not built):** auto-confirm (never without an explicit decision), "new run waiting" push (the natural trigger to revisit R3.5), Partner-API webhooks, FIT/lap splits, health/recovery ingestion, cycling. | Removes the human-plus-LLM pipe from run logging; the app can no longer go quietly stale without saying so. | RA2.1/RA2.2 (auth, online-only writes), R2.7 T2 (field population) | Medium-high |

**Order within R5:** 5.2 and the R5.1 contract spike can start once R2 lands; 5.3 anytime after R2.4; 5.4/5.5 follow data needs, not a schedule.
**Updated 2026-10-10 (scoping, not scheduled):** R5.3 first (small, closes the loop, fixes the cost/km gaps). Then R5.5.1–5.5.3 (read-only over data that exists) and R5.4.1 location; these two are independent, either order. R5.4.2 weather's free half (archive projection) rides with R5.4.1; its external half, and R5.4.3 splits, build only when an R5.5 view asks for them. Injury context is parked (see the note at the end of §R5.5).

### §R5.3 — Purchase-loop closure ("Bought it")

**Status: ✅ built 2026-10-10** (B21; migration `b1c2d3e4f5a6`). The service lives in `services/purchase_draft.py`, not rotation.

**Today:** `owned_shoes` already has `purchase_price` and `purchase_date`, but they're mostly empty (July DB snapshot: price on 14 of 23 shoes, date on 4). A deal knows brand, model, retailer, `current_price`, URL and `sizes_available`. Nothing connects a deal to the add-shoe flow, and B1 says nothing may connect them in the schema.

**Add:**
- **Provenance as plain strings, not an FK (B1 holds):** `owned_shoes.purchase_retailer` (String, nullable) and `purchase_url` (Text, nullable). One reversible migration, no data movement. Deleting the watchlist entry or the deal can never touch the owned shoe. Record it as a new decision (`design_decisions.md`, "purchase provenance is a recorded fact, not a relationship") with B1 cited.
- **Service (read only):** `services/purchase_draft.purchase_draft_from_deal(db, deal_id) -> PurchaseDraft`, with brand, model, price paid = the deal's `current_price`, `purchase_date` = today (Toronto), retailer name and URL. Saving goes through the **existing** owned-shoe create path, which gains the two optional fields. No new writer.
- **REST + MCP parity:** `GET /api/deals/{id}/purchase-draft` and the MCP read tool `draft_purchase_from_deal`, both over the same service function. **Correction (found while building, 2026-10-10):** no MCP tool creates an owned shoe, and `add_shoe` is the watchlist, so the two new fields are not on any MCP tool. Saving happens in the app; Son of Anton can draft a purchase but cannot save one.
- **UI:**
  - **Bought it** on the deal sheet opens the add-shoe dialog filled in. Every field stays editable, since the price paid often differs (coupon, size, in-store).
  - After saving, an optional **"Stop watching <model>?"** prompt. It defaults to no; when accepted it uses the existing watchlist delete, so interest dies by choice, never as a side effect.
  - Shoe detail shows "Bought at <retailer> for $X" with the link.

**Not in scope:** an FK or "converted" state on the deal; auto-creating shoes; marking a deal "used"; buying flows for shoes you don't run in.

**Exit:** Bought it → prefilled form → saved shoe shows its provenance and a cost/km from day one. The watchlist is untouched unless you said so. Tests cover the draft, the create path with/without provenance, and REST = MCP. Desktop + 380 px pass.

### §R5.4 — Richer ingestion (location, weather, splits)

Four candidates, each with its own gate. One fact shapes all of them: **R8.2 already reads every run's per-second stream** (the 694 Strava archive FIT/GPX files via `scripts/backfill_best_efforts`, and COROS FIT downloads a few per poll tick), keeps the best efforts, and throws the rest away. Location and splits are mostly "keep more from a read we already do".

**R5.4.1 — Location on activities** *(added at the runner's request, 2026-10-10; ✅ built 2026-10-10, B22)*
- **Sources:**
  - (a) The FIT/GPX streams R8.2 reads carry GPS fixes (FIT `position_lat/long` in semicircles, GPX `trkpt lat/lon`). `fit_stream`/`gpx_stream` currently parse only time + distance, so extend them to also return the first valid fix.
  - (b) The COROS list response prints a `Location:` place label per run (redacted in `tests/fixtures/coros/`). `parse_sport_records` currently ignores it, so capture it as a pinned, fixture-tested field like the others.
  - (c) The Strava CSV has no coordinates; archive runs get theirs from (a).
- **Storage:** `activities.start_lat`, `start_lng` **rounded to 3 decimals (~100 m)**, plus `location_label` (String, from COROS). **Never tracks or polylines.**
  - Why rounded: most runs start at home, and the data lives on a VPS and is readable by LLM clients. 100 m is enough for weather and "where", not for an address.
  - MCP outputs expose the label, not the coordinates, by default.
  - Record both choices as a decision.
- **Write path:** the R8.2 scan today touches only effort tables ("none of this touches runs"). Writing location makes it update **two location columns on the activity row**. It still never writes distance, time, attribution or mileage (INV-1/INV-2 unchanged). Say so in the docstring and test it.
  - For COROS runs, the label also has to be carried on `pending_coros_runs` so a confirm can stamp it.
- **Backfill:** one more pass with the existing archive scan script, which already walks the export folder and fills best efforts and location in a single walk. COROS runs fill on the poll tick's scan.
- **Answers:** where do I run (home loops vs travel vs race venues); trail vs road context next to elevation. It's also the **prerequisite for R5.4.2's weather lookup**.
- **Later, not v1:** runner-named places (cluster nearby start points → "Mont Royal", "canal loop"), instead of reverse geocoding through an outside service.

**R5.4.2 — Weather at run** *(free half ✅ built 2026-10-10, B23; external lookup parked 2026-10-10 (heat analysis))*
- **Free half (no new service):** the Strava export already contains weather columns, kept in `raw_json` since import (`Weather Temperature`, `Apparent Temperature`, `Humidity`, `Wind Speed`, …). July snapshot: on **172 of 694 runs (2024-02 → 2025-10)** (July snapshot; the 2026-10-10 reconciliation found 215 rows with raw weather), plus watch-sensor `Average Temperature` on 196.
  - Project them into typed columns (`weather_temp_c`, `apparent_temp_c`, `humidity_pct`, `wind_speed_m_s`; built as m/s, the export's unit, checked on real values) with a migration that reads `raw_json`. This is the "ingest raw, model later" escape hatch paying off.
  - **Check units on real values first**; don't assume °C or km/h.
- **External half (new runs):** COROS runs carry no weather, so they need a historical-weather lookup keyed on start coordinates + start time. Open-Meteo's archive API is free and keyless, and is the first candidate.
  - This would be Anton's first outbound call of this kind: spike + decision entry before building.
  - Degrades to null (missing ≠ error).
  - Depends on R5.4.1.
- **Gate — checked 2026-10-10, not met → parked.** Heat analysis on the archive (read-only, July DB copy): 215 activities carry weather, 172 are runs, 111 are steady runs (form-trend filter). Raw medians dip at ≥ 26 °C (1.329 m/beat vs 1.414–1.426 at 18–26 °C, n = 22), but the dip doesn't survive controls: vs cooler runs within ±14 days the hot runs are −0.3 % (64 % slightly worse); a fit on temperature + time trend + distance gives −0.3 % per 10 °C (inside noise; humidity adds nothing); within-month hot-vs-cool is +0.9 % (6 months). The raw dip is fitness, not heat: efficiency rose ~6 %/year and every ≥ 26 °C run is from Jun/Aug/Sep 2025. Only faint signal: feels-like ≥ 30 °C, 1.329 vs ~1.40, n = 10. **Decision:** don't build the external lookup or heat-adjusted efficiency. Revisit only with a real hot-weather sample (cheap test: note "felt the heat" in run descriptions on ≥ 30 °C days next summer). See §Parked & gated.

**R5.4.3 — Splits / laps / HR** *(✅ built 2026-10-20, B28, reopened by R11.6: time, HR and elevation per km; HR curves are still not stored)*
- **What to keep:** per-km splits (time, avg HR, elevation change) from the same streams, in an `activity_splits` table. Like best efforts, that's derived data that has to be stored because the source files aren't in the DB, so it's a B19/INV-7-style exception and needs that note. HR curves aren't stored; splits are enough for the questions below.
- **Gate:** build when an R5.5 view needs it, e.g. negative-split analysis of long runs, or HR drift (aerobic decoupling) on steady runs. Not for its own sake.

**R5.4.4 — Periodic Strava re-exports**
- **Already true:** the importer is idempotent on `strava_activity_id`, so a new export updates in place.
- **Gap:** a runbook, not code: where to drop the export, which script to run, then re-run the archive scan. Low value now that COROS is the primary source; docs only, whenever you do one.
  - **Runbook (written 2026-10-10; run from `backend/` with the venv):**
    1. Copy the new export folder to the host. The path is the runner's choice; it must contain `activities.csv` and the `activities/` folder.
    2. `venv/bin/python -m app.scripts.import_strava --csv <export>/activities.csv` (takes the CSV path, not the folder). Idempotent on Strava activity ID; fills the weather columns.
    3. `venv/bin/python -m app.scripts.backfill_best_efforts --export-dir <export> --rescan` walks `<export>/activities/` and fills best efforts and start location. `--rescan` is needed once so runs scanned before R5.4.1 get a location; it is idempotent. Exit code 1 means some runs failed; the summary lists them.
    4. Optional: `venv/bin/python -m app.scripts.infer_archive_tags` prints the dry-run plan and writes nothing. Run `--apply` only after reviewing that output.

### §R5.5 — Longitudinal analytics

**Status (2026-10-10):** R5.5.1 and R5.5.2 built (`services/insights.py`, REST + MCP, the shoe-page card). R5.5.3 dry run built; apply pending the runner's review.

**Today:** R8.4 shipped the first longitudinal reads:
- the load trend (7 vs 28 days);
- the form trend (m/beat on steady runs);
- best efforts inside runs;
- race readiness.

The data for shoe-level analysis is there:
- July snapshot: 679 runs attributed to a shoe;
- ~97% of runs carry avg HR.

Run-type tags are nearly empty (7 of 938). T8 infers them only from COROS run names.

**Phase 1 — read-only, no schema** (one service, e.g. `services/insights.py`; REST + MCP tool over the same functions; heuristics labeled as in B20):
- **R5.5.1 — Shoe performance.** Per pair, and per model across pairs: runs, km, median efficiency (m/beat, reusing `form_trend`'s steady-run filter), pace and HR.
  - **The honesty problem:** raw pace by shoe mostly measures *what you used the shoe for* (race shoes look fast because you race in them). Compare **steady runs only**, show the run count behind every number, and refuse a verdict under a minimum sample.
  - Surfaces: a "How it runs" card on shoe detail; Son of Anton can answer "is the Evo SL actually more efficient than the Novablast?".
- **R5.5.2 — Wear curves.** Km per week over each shoe's life. For retired shoes, the final km vs. `mileage_limit`, rolled up by `shoe_type` ("your tempo shoes last ~620 km").
  - Feeds a **suggested** default `mileage_limit` on new shoes (suggested, never set) and sharpens the R6.2 forecast.
- **R5.5.3 — Tags for the archive.**
  - **Inference:** extend T8's inference (same controlled vocabulary, `utils/activity_tags.py`) to Strava run names, plus any Strava type fields already in `raw_json` (it has a `Long Run` column; check what else).
  - **This is a write, and tags drive PB eligibility (R8.1).** It ships as a backfill script with a **dry-run diff you review**, including which PBs would move, before applying. Never silent.
  - **Unlocks:** "race pace trend over 3 years", "workout frequency vs PB trajectory".

**Phase 2 — needs R5.4:**
- heat-adjusted efficiency (weather, R5.4.2);
- by-place views (location, R5.4.1);
- negative splits / HR drift (splits, R5.4.3).

**Exit (phase 1):**
- Every number is the same on REST, MCP and the UI.
- Sample sizes are shown.
- The tag backfill is applied only after your review.
- Tests cover the steady-run filter, the minimum-sample refusal and retired-shoe wear math.

**Injury context — parked (runner, 2026-10-10: "not needed for now"). Notes on where it would fit if it ever earns a place:**
- **It isn't a shoe note.** Shoe notes are per pair; injuries are per runner. The smallest honest form is a **niggle log**: dated free-text entries with an optional body area (e.g. "left calf") and a 1–3 severity. It sits next to runs, not inside them, and is never a medical record.
- **The value is in correlation, not storage.** Mark niggles on the R8.4 load chart, then let Son of Anton look back across flare-ups: "the last three left-leg flare-ups followed a week above 1.3× load" or "…the first two weeks in a new shoe". Both inputs already exist (load trend, attribution dates).
- **The felt-need check is behavioural:** would you log a niggle within a day of feeling it? A log that's filled in after the fact misleads more than it helps. A cheap test needs no code: jot niggles in run descriptions for a month and see if the habit holds.
- **A zero-effort neighbour:** COROS already exposes recovery status, HRV and resting HR (deferred under R5.7 as "health/recovery ingestion"). Those signals arrive without manual logging, and would be the first thing to correlate with a niggle log if both existed.
- **Sensitivity:** health data. If built, keep it out of MCP resources and default tool outputs unless asked for.

---

## R6 — Daily-use improvements *(scoped 2026-10-08 — not scheduled)*

*From a project-state review on 2026-10-08: the platform is built (R5.7 means runs now arrive on their own), so the next value is in making what exists more useful day to day, not in new surfaces. Every item carries a felt-need check; per the standing rule, build only when the check comes back positive. R6.1 is the exception — it's maintenance with a known cost.*

| # | Item | Description | Why it matters | Felt-need check | Dependencies | Complexity |
|---|---|---|---|---|---|---|
| R6.1 | **`project_state.md` top-section refresh** – ✅ **Done (2026-10-08)** | Rewrite the stale sections the 2026-10-08 review found: §1 summary ("all local, no auth", "RA1.5 is the next human task", retailer count), §5 "Planned" (lists shipped R3.1/R3.2/R2.1/R4.1/R2.6), §6 quirk 5 (per-browser checkpoint state — fixed by C10), §7 top debt ("no auth" — fixed by R2.1→E9/E10), §10 branch assumption (HEAD is not always `main`). Docs only. | This file is "read this first" for every session; a fresh session currently starts from a July picture. | None needed — known drift. | — | Low |
| R6.2 | **Retirement forecast → deal radar** – ✅ **Done (2026-10-08)** | Add a projected limit date to each retirement-pipeline shoe from its recent usage, and surface replacement deals *before* the shoe is done. Detail in §R6.2. | Joins the two halves of Anton — rotation and deals — in the one way no other tool can: "Evo SL Teal hits its limit in ~5 weeks; 3 replacements are on sale now." | Has a replacement been bought late or at full price because the shoe's end crept up? | R4 retirement pipeline (`rotation.retirement_pipeline`), R3.2 replacement alerts | Low–Medium |
| R6.3 | **My-size deal filter** – ✅ **Done (2026-10-08)** | A stored size preference; deals, the watchlist and the deal-alert digest filter (or rank) by whether `sizes_available` contains it. Detail in §R6.3. | Deals that don't come in your size are noise in the feed and in every digest. | How often does a deal you open turn out not to have your size? | `sizes_available` on `deals`/`price_records` (exists) | Low |
| R6.4 | **"New run waiting" push** (R3.5 revisit) – ⏸ **Step 0 measured 2026-10-08: not built** (1 run, 0.1 d lag, 0 waiting) | Web Push from the backend to the installed PWA when the poller queues a run. One event type only. Detail in §R6.4. | R5.7 made runs arrive unattended, but the inbox still waits for you to open the app; R5.7 itself named this as the R3.5 revisit trigger. | **Measured, not guessed:** `pending_coros_runs.first_seen_at` → `resolved_at`. If confirmations routinely lag by days, build it. | R5.7 inbox, RA2.2 PWA | Medium |

**Order within R6:** R6.1 anytime (one short session). R6.3 before R6.2 if both pass their checks — the size preference makes the radar's replacement list honest. R6.4 runs its measurement first (a query, no code) and builds only on a positive result.

### §R6.2 — Retirement forecast → deal radar

**Today:** `rotation.retirement_pipeline` returns active shoes at ≥ `RETIREMENT_THRESHOLD` (0.75) of `mileage_limit`, worst-first, with `replacement_deals` = active deals on tracked shoes of the same `shoe_type` (there is no FK owned → tracked shoe). Home's `_shoe_alerts` is a thin projection over it; `deal_alerts._find_replacement_alerts` bridges the same two domains for the digest.

**Add:**
- **Forecast (pure, server-side — A4):** per active shoe, recent weekly km = attributed distance over the last N weeks (start with 6) ÷ N; `weeks_to_limit = (mileage_limit − current_mileage) / weekly_km`; `projected_limit_date`. No recent use → `idle` (no date, not "never"). Over the limit → `overdue`. Lives in `rotation.py` next to the pipeline so Home, the REST API and MCP read one number.
- **Query on `Activity` columns with `contains_eager(ShoeRun.activity)`** — the `ShoeRun` proxy fields don't work in `filter()` (project_state §6 quirk 2).
- **Radar window:** include shoes whose projected date falls inside a lookahead (e.g. 8 weeks) even if still under 75% — a high-mileage week can take a shoe from 70% to done before the threshold notices. Keep the 75% band as-is; the forecast widens it, doesn't replace it.
- **Surfaces:** Home shoe alert shows "~5 wks" next to the bar; `/shoes/:id` replacement-deals card shows the date; the deal-alert digest's replacement section sorts by projected date. MCP: add the fields to the existing pipeline/rotation outputs rather than a new tool.

**Not in scope:** model-specific wear curves (that's R5.5), auto-retiring, auto-buying.

**Exit:** a shoe at 70% with a heavy recent block appears with a date; an idle shoe shows no date; numbers match across Home, REST and MCP; tests cover idle, overdue, no-limit and the lookahead edge.

### §R6.3 — My-size deal filter

- **Preference:** one `AppSettings` key (e.g. `preferred_shoe_size`) via the existing `services/settings.py`; a Settings field to set it. Single value first; a per-brand override map only if brand sizing actually differs in your rotation.
- **Matching:** normalise size labels before comparing — scrapers emit retailer-specific labels (`10`, `US 10`, `M10`, `10 D`…). One pure normaliser in `app/utils/` with tests drawn from real `sizes_available` values in the live DB (sample them first; don't guess the formats). Youth labels are already excluded at scrape time (`_is_youth_size`).
- **Behaviour:** default = rank in-size deals first and badge out-of-size ones; a toggle hides them. The deal-alert digest counts only in-size deals for new-deal and price-drop alerts. Empty `sizes_available` = unknown → treat as "maybe", never silently hide.
- **Not in scope:** changing deal qualification (B9-v3/D8 stay size-agnostic — a deal is a deal; size is a per-runner view).

**Exit:** with a size set, the Deals page and digest reflect it; with none set, behaviour is unchanged.

### §R6.4 — "New run waiting" push (gated R3.5 revisit)

**Step 0 — measure (no code) — ✅ run 2026-10-08 on Hetzner: 1 resolved run, mean/max lag 0.1 days (~2.4 h), 0 still waiting. Negative result, but n=1; re-run after a few weeks of real use (query in the 2026-10-08 changelog entry) before closing this for good.** query `pending_coros_runs` for `resolved_at − first_seen_at` over the first few weeks of R5.7 use. Build only if runs regularly sit for days or get forgotten.

**If built:**
- **Web Push (VAPID)** to the installed PWA — iOS supports it for Home-Screen-installed web apps, so no native app is needed (keeps R5.1 parked).
- **Backend:** `push_subscriptions` table (endpoint + keys, one row per device), subscribe/unsubscribe endpoints behind the session cookie, VAPID keys in `backend/.env`, a send helper called by `coros_poller` *after* it queues new rows (the poller stays a non-writer of runs — INV-1/INV-9 unchanged). Coalesce: one notification per poll that found runs, not one per run.
- **Frontend:** the SW is currently `vite-plugin-pwa` `generateSW` (`registerType: 'autoUpdate'`); a push handler needs custom SW code — either `workbox.importScripts` for a small push/notificationclick script or a switch to `injectManifest`. Pick the smaller change at build time. Opt-in button in Settings (iOS requires a user gesture to request permission). Tapping the notification opens the New runs inbox.
- **Not in scope:** any other event types (deal alerts, scrape failures) until this one proves its worth; email; auto-confirm (still never without an explicit decision — C9).

**Exit:** a run recorded on the watch produces one notification on the phone within one poll interval; tapping it lands on the inbox; unsubscribing stops them.

---

## R7 — Polish & coverage *(added + scheduled 2026-10-09 — the active milestone)*

*Picked by the runner on 2026-10-09 from the follow-ons left by the mobile UI review (PR #42/#43) and the long-standing coverage gap. Unlike R6, these are **scheduled**, not gated on a felt-need check — the runner's pick is the check. Execute in order; one session per item; one commit per numbered task.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R7.1 | **Design cleanup** – ✅ **Done (2026-10-09)** | Close the debt the `DESIGN.md` review left open: Tailwind `/opacity` modifiers on `var()` colour tokens, hard-coded hex in charts, emoji in UI copy, `--faint` contrast. Detail in §R7.1. | One of the four is a silent correctness bug (styles that never render); the rest break CLAUDE.md §5's "no hard-coded hex" rule and the design system. Do it first — R7.2 builds new UI on the same tokens. | `DESIGN.md`, `index.css` tokens | Low |
| R7.2 | **Confirmation card in chat** – ✅ **Done (2026-10-09)** | When Son of Anton proposes a write (log a run, confirm a COROS run, retire a shoe, save a review…), the chat shows a structured card with Confirm / Edit / Cancel instead of asking for a typed "yes". Detail in §R7.2. | Turns C9's confirmation gate from prose into a control: it can't be confirmed by accident, and what's confirmed is exactly what gets written. It's the main thing the phone mockups had that the build doesn't. | R7.1 (tokens); `chat_service` SSE stream; existing MCP write tools | Medium |
| R7.3 | **Scraper coverage — Sport Experts** – ✅ **Done (2026-10-09): marked unscrapable** (Imperva blocks headless Chromium from Hetzner) | Bring Sport Experts (FGL / Canadian Tire custom platform) from "future" to scraping or to an honest `mark_unscrapable`. Sporting Life stays declined (Cloudflare; D3). Detail in §R7.3. | Last unbuilt retailer; the deal feed silently excludes it today (project_state §6 quirk 4). | R4.6 onboarding agent (`probe_retailer`), `add-retailer` skill (S05) | Medium (spike-gated) |
| R7.4 | **Scraper coverage — Boutique Courir** – ✅ **Done (2026-10-09)** *(added same day at the runner's request, after a re-probe)* | Bespoke WooCommerce scraper: search HTML + product JSON-LD (the Store API is login-gated). | Last open custom retailer with no bot wall. | `add-retailer` skill (S05) | Low |

**Order within R7:** 7.1 → 7.2 → 7.3. 7.1 is small and clears the token problems before 7.2 adds UI. 7.3 is independent of both and can be swapped forward if the spike is wanted sooner.

### §R7.1 — Design cleanup

Scoped 2026-10-09 with greps over `frontend/src`; re-run them at session start, since counts drift.

1. **`/opacity` modifiers on `var()` tokens (correctness first).** 57 `/N` modifier uses across 25 `.jsx` files. The ones on token colours (`bg-primary/90`, `border-primary/30`, …) generate nothing, because the theme colours are bare `var(--x)` values Tailwind can't split into channels. Ones on literal palette colours (`black/50`) are fine. **Fix the theme, not every call site:** define the tokens so Tailwind can apply alpha (for example, channel-valued variables with `rgb(var(--x-rgb) / <alpha-value>)` in `tailwind.config`, or `color-mix()`), then check each existing use renders as intended. Some were written against the broken behaviour and may look wrong once they start working.
2. **Hard-coded hex → tokens.** `PriceChart.jsx` (12), `training/VolumeChart.jsx` (5), `ShoeProductCard.jsx` (2). Recharts takes colour strings, so read the CSS variables at render time (a small `lib/` helper over `getComputedStyle`) instead of duplicating values.
3. **Emoji out of UI copy.** `LogRunDialog.jsx`, `training/PlannedRacesCard.jsx`, `ScrapabilityTestModal.jsx`, and any toast strings. Replace with lucide icons or plain text, per `DESIGN.md`.
4. **`--faint` contrast.** It's `#6a6f76` today, about 3.7:1. Raise it to ≥ 4.5:1 against both surfaces it's used on, in light and dark, or restrict it to non-text uses.

**Exit:** all four greps come back clean (or every remaining hit is a literal palette colour, listed in the changelog entry). `vite build` clean, 0 console errors, desktop + ~380 px pass on the screens touched. No backend change, so the suite is unchanged.

### §R7.2 — Confirmation card in chat

**Today:** `chat_service` streams `text`, `tool_call`, `error` and `done` SSE events, consumed by `useChatStream`. C9 confirmation happens in prose: the model describes the write, the runner types "yes", and the model calls the write tool.

**Add:**
- **A `proposal` SSE event.** Emitted when the model is about to call a confirm-gated write tool. It carries the tool name, the exact arguments, and a human summary (the runner-facing fields: shoe, date, distance, pace, and so on). It should piggyback on the existing MCP write tools, not a parallel path (CLAUDE.md §2.2). The design question to settle first is how the proposal is produced: intercept the model's `tool_use` for write tools and hold it pending, or use an explicit `propose_*` step. Record the choice in `design_decisions.md`.
- **Confirm executes exactly the proposed call.** The card's Confirm executes the held tool call with the proposed arguments, through the same MCP tool and the same sanctioned service path (`rotation.log_run`, `coros.confirm_run`, …). Edit opens the existing dialog prefilled (for example `LogRunDialog`). Cancel sends the decline back to the model. Nothing is written without the tap (INV-8 / C9 unchanged). The SSE event name is a hand-matched string contract on both sides (CLAUDE.md §6).
- **UI:** a card in the thread, mono details, 44 px targets, matching the PR #42 phone mockups. After the tap it collapses to a one-line result ("Logged 12.4 km to Evo SL").
- **Online-only writes:** Confirm is a write, so it follows the RA2.2 boundary: disabled with a message when offline, never queued.

**Not in scope:** auto-confirm (never without an explicit decision — C9); proposals for read tools; Claude Desktop / claude.ai (they keep their own client-side confirmation; this is Son of Anton only).

**Exit:** a chat-initiated run log shows a card, and Confirm writes exactly one activity with the right mileage delta (test it). Cancel writes nothing; a double tap doesn't write twice (idempotent). Tests cover the event shape and the gate. `vite build` clean; desktop + ~380 px pass; verify against a live model with keys, not just a keyless backend.

### §R7.3 — Scraper coverage: Sport Experts

- **Step 0 — spike (no committed code).** Run `probe_retailer` (R4.6) on Sport Experts to confirm it isn't Shopify or Algolia. Then look at how the site delivers prices: a JSON/search API behind the product grid (preferred), server-rendered HTML, or JS-only (Playwright). Also check the bot protection, the `/en` locale, and whether a known shoe resolves. Write the findings in the changelog entry.
- **If scrapable:** a bespoke scraper in its own file, subclassing the right base and registered in `registry.py`, following the S05 `add-retailer` skill. Keep the politeness sleeps and the kids filter (`search_products_filtered`). Verify with the `POST /shoes/test` dry-run and a real `scrape_runs` row; don't write HTML-fixture tests (CLAUDE.md §10).
- **If not:** `mark_unscrapable` with a specific reason (the Sporting Life precedent), so the watchdog and the onboarding queue stop listing it. That is a valid outcome, not a failure.
- **Sporting Life:** unchanged. Paid unblocking stays declined (D3); don't fight Cloudflare.

**Exit:** Sport Experts either appears in `scrape_health` with successful runs and real deals in the feed, or is marked unscrapable with a documented reason. Update `architecture.md`'s retailer table either way.

---

## R8 — Training page: records, races & dashboards *(scoped 2026-10-09 — not scheduled)*

*Raised by the runner on 2026-10-09 from daily use of the Training (fitness) page. Start with records and past races; the dashboards (R8.4) get their own planning session. Grounded in a code read of `services/strava_stats.py`, `utils/activity_tags.py` and `services/races.py` the same day.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R8.1 | **Records: who counts, and on what clock** – ✅ **Done (2026-10-09)**: two lists (runner's choice), elapsed clock, ratio guard retired (B18) | Rewrite PB eligibility so the tag means what the runner expects, and time records on **elapsed** time, not moving time. Detail in §R8.1. | Today a run stays a record after its Race tag is changed to anything except Intervals/Track — the rule is "eligible unless excluded", the opposite of what the runner expects. Moving time also flatters stop-heavy runs. | R2.7 T1/T3 (tags, current rule) | Low |
| R8.2 | **Best efforts inside longer runs (Strava-style)** – ✅ **Done (2026-10-09)**: spike GO → built (segments 1k → full, intervals count, archive backfill + COROS FIT in the poll tick; B19). Prod: run the backfill after deploy | Find the fastest 5k / 10k / half *segment* inside any run (e.g. a 5k PB set during a 10k race) from per-second data, stored per activity. Detail in §R8.2. | Whole-activity bands can never see a 5k inside a 10k. This is how Strava, COROS and Garmin do best efforts. | R8.1 (eligibility + elapsed clock); spike S1 | Medium–High |
| R8.3 | **Past races with no run attached** – ✅ **Done (2026-10-09)**: build was current; a run that day kept the race; past-race actions added (link the run / mark skipped / delete) | Make sure a plan that didn't happen leaves "Past races": confirm the B17 prune (PR #43) is live in production, then decide whether the rule should be stricter. Detail in §R8.3. | "Parkrun Time Trial" (planned, 2026-07-18, no activity) still shows in production on 2026-10-09, 83 days later. | B17 `races.prune_unrun_races`; RA3 would prevent "merged but not deployed" | Low |
| R8.4 | **Training dashboards rework** – ✅ **complete (2026-10-09)** — five tasks, see §R8.4 | Answer three questions at the top of the Training page — *am I building or holding?*, *what's my form now?*, *am I ready for my next race?* — and keep every current card below them. Detail in §R8.4. | Runner: "the dashboards need a lot of work." Today the page shows totals and a latest snapshot, but no trend or verdict. | R8.1–R8.3 (records and races feed the page) | Medium–High (5 tasks, 2–3 sessions) |

**Order within R8:** R8.3 step 1 first (a deploy check — minutes). Then R8.1 (small, fixes the visible bug). R8.2 starts with its spike and builds only if the spike shows the data is there. R8.4 was planned 2026-10-09 (§R8.4): five tasks, R8.4.1 spike first. R8.4.1–R8.4.5 all ✅ (2026-10-09) — **R8 is complete.**

### §R8.1 — Records: who counts, and on what clock

**Outcome (2026-10-09):** shipped as proposed with the runner's choice of **two lists** — Race PBs (Race/Parkrun or race-linked) and Best efforts (all but Intervals/Track), behind a toggle on the Records card; elapsed clock with a flagged moving fallback; ratio guard retired; race results from runs on the same clock; `get_personal_bests` returns `race_pbs` + `best_efforts`. Also: a completed race with no run attached can now be linked from the Races card, so it counts as a Race PB. Decision B18 (supersedes B16).

**Today (code read 2026-10-09):** `strava_stats.personal_bests` recomputes on every request from `unified_activities`: whole-activity time within a distance band (5k ±0.3 km, 10k ±0.5, half ±1.0, full ±1.5), fastest wins. Eligibility comes from `activity_tags.pb_exclusion_reason`: `Intervals`/`Track` excluded; **every other tag eligible**; untagged runs excluded only if `elapsed > 1.5 × moving`. Time is `_effective_moving_s` — **moving** time. So re-tagging a race from `Race` to `Tempo`/`Easy`/`Workout` leaves the record in place — the reported bug is the rule working as written.

**Change:**
- **Clock → elapsed time** (gun time; what Strava uses for best efforts and what race results mean). Moving time stays for pace/volume elsewhere. This alone defeats the original T3 false-PB case: a stop-heavy interval session's rests count against it. Falls back to moving time only when elapsed is missing, and says so in the response.
- **Eligibility — decision for the runner (default proposed):** split into two lists on the card:
  - **Race PBs** — official results: activities tagged `Race` or `Parkrun` (and races linked via `planned_races.activity_id`). Re-tagging removes the result immediately (records are computed live).
  - **Best efforts** — fastest efforts from any run except `Intervals`/`Track` (whole-activity until R8.2 lands, then segments).
  - *Alternative if the runner prefers one list:* race-only (`Race`/`Parkrun`), dropping training runs entirely.
- **Retire the 1.5× ratio guard** once the elapsed clock is in (it was the moving-time workaround); keep `excluded_count`/`excluded_reason` for whatever exclusions remain.
- **Same clock for race results:** synthetic past races (`races.list_races`) report `result_time_s = moving_time_s`; switch to elapsed for consistency.
- **MCP:** update `get_personal_bests` (and its "whole-activity, not segment" docstring caveat once R8.2 ships).

**Exit:** re-tagging a race to a training tag removes it from Race PBs on the next load; an interval session with standing rests can't top a band; tests cover each tag class, missing elapsed time, and the two-list split.

### §R8.2 — Best efforts inside longer runs

**Spike S1 result (2026-10-09): GO** — see the best_efforts spike report (retired). All 694 archive runs have 1 s FIT/GPX streams; COROS FIT files come from an unsigned S3 URL via `queryActivityFitFileDownloadUrls`; `fitdecode`/`gpxpy` are dependency-free. Before the build, the runner decides: intervals in segment efforts, 1k/mile bands, segments in Best efforts, and FIT-URL handling.

**Feasible, with one data question.** Exact best efforts need per-second (or per-record) distance + time streams; laps are only an approximation (fastest N consecutive auto-laps, exact only when laps are whole km).

**Spike S1 (no product code) — answer three questions:**
1. **COROS runs:** can the backend's COROS MCP client fetch a FIT file? The COROS MCP server exposes `queryActivityFitFileDownloadUrls` / `downloadActivityFitFiles` (and `queryActivityLapData` as a fallback); `coros_mcp_client` currently calls only `querySportRecords` and `getActivityDetail`.
2. **The 8-year Strava archive:** the runner's Strava bulk export still has an `activities/` folder (`~/Workspace/export_33354574/`), and `Activity.fit_filename` links archive rows to file names. Check the formats (`.fit.gz` / `.gpx` / `.tcx`) and coverage before promising backfill.
3. **Parser:** a FIT decoder (e.g. `fitdecode`/`fitparse`) + GPX handling inside the A7 pin set; verify it installs in the Docker image.

**If the spike passes:**
- **New table `activity_best_efforts`** (`activity_id` FK, `distance_label`, `elapsed_s`, `start_offset_m`, `source` = fit|gpx|laps) — one row per standard distance per activity. Additive E4 migration. Derived data: recomputable, never hand-edited.
- **Pure sliding-window function** in `app/utils/` over the distance/time stream (two pointers; elapsed time for the segment). Tested against hand-built streams and a known race file.
- **Compute at confirm time** for new COROS runs (inside the single-writer path's caller, after the run lands — the poller stays a non-writer); **one-off backfill script** for the archive. Raw files are not stored in the DB — parse and keep only the efforts.
- **Records read efforts** for "Best efforts" (R8.1's second list); Race PBs stay whole-activity race results.
- **GPS honesty:** cap implausible segments (e.g. faster than a sanity pace) and allow excluding an activity from records — GPS drift in a 10k can fake a 5k.

**Exit:** a 5k effort inside a 10k race shows as the 5k best effort with the 10k activity linked; Sunday's marathon (2026-10-11) is the natural test case — it should yield 5k/10k/half efforts.

### §R8.3 — Past races with no run attached

**Outcome (2026-10-09):** step 1 found the build current; production has a COROS run on 2026-07-18 (8.83 km, a normal run), so B17 rightly kept the race. Step 2, the runner's choice: keep the rule, and give past races **Link the run / Mark skipped / Delete** in the app (`POST /races/{id}/link-activity`). "Spring Half" (completed, unlinked) stays as the runner's record. Design decision B17 updated.

**Today:** B17 `races.prune_unrun_races` (PR #43, 2026-10-08) deletes a race only when it is still `planned`, has no linked activity, is ≥ 3 days past, has **no activity of any kind on that date**, and no pending COROS run that date. It runs whenever races are listed. On a DB copy it pruned "Parkrun Time Trial"; in production on 2026-10-09 it is still listed (`planned`, 2026-07-18, `activity_id` null).

**Step 1 — deploy check (minutes):** most likely the server is running a build from before PR #43. On the server: `git log -1 --oneline`, and if it predates #43, `git pull && docker compose up -d --build`. Opening the Training page then prunes it. If the build *is* current, the blocker is an activity on 2026-07-18 (any run that day counts as "might have been the race") — go to step 2.

**Step 2 — decisions for the runner:**
- **"Any activity that day" vs "linked activity only."** The current rule spares a race if *any* run happened that day (it might have been the race, unlinked). Stricter option: prune whenever nothing is linked, after the grace period — simpler, but deletes a race you ran and forgot to link.
- **Completed races with no activity.** "Spring Half" (2026-04-19) is `completed` with a typed result and no linked run — it's kept today. Options: keep (it's your record), offer a "link to activity" prompt, or treat it like an unrun plan.
- **Prefer a status over a delete?** `skipped` already exists; auto-marking `skipped` instead of deleting keeps history visible but out of "Past races".

**Exit:** no planned-but-unrun race appears in "Past races" past the grace period in production; the chosen rule is recorded in design_decisions (B17 update).

### §R8.4 — Training dashboards rework

**Planned 2026-10-09** with the runner. The runner's choices:
- **Questions the page answers at a glance:** building or holding, form now, ready for race X.
- **Not chosen:** a block-vs-block comparison.
- **Cards kept:** all of them (Volume chart + tiles, Races + Records, Fitness + Predictions, Activities). The rework *adds* answers on top; it doesn't remove cards.

**What the data supports** (local DB, 710 runs):

| Data | Coverage | What it means for the plan |
|---|---|---|
| Distance, time, pace | Every run since 2018 | Usable everywhere |
| Avg HR | 692 runs | Usable for the form trend |
| Elevation | 704 runs | Usable |
| R8.2 best efforts | Scanned runs | Usable for the form trend |
| COROS `training_load` | 10 runs, all since June 2026 | Load is measured in **km/time**, not COROS load |
| Activity tags | 7 runs | Nothing may *require* a tag; use tags only where present and the runner can fix them |
| `athlete_metrics` | 1 row; append-only, but only written by the manual `sync_fitness` prompt | No VO₂ max or threshold history to chart until something records snapshots regularly |

**Rules:**
- Every number and verdict is computed server-side in one place, with REST + MCP parity (CLAUDE.md §2/§4).
- Nothing new is stored except the fitness snapshots in R8.4.1.
- Mobile-first: answers go first at 380 px.
- Chart forms follow the `dataviz` approach.

| # | Task | Detail |
|---|---|---|
| R8.4.1 | **Record fitness automatically** – ✅ **shipped (2026-10-09)**: spike GO (the fitness_snapshots spike report (retired)), then built — parser + poll-tick capture, saved only when changed (C13) | **Spike first:** capture `queryFitnessAssessmentOverview` from the COROS MCP server and check it gives VO₂ max, threshold pace, running level and predictions. If it does: add a fixture-pinned parser to `coros_mcp_client` (prose, anchored regexes — CLAUDE.md §6 trap) and pull fitness inside the same COROS sync as runs (`coros_poller.run_tick`: the scheduled tick and **Sync now**), saved without confirmation (runner's call) — fetched when the tick finds a new run, on a manual sync, and once a day as a fallback; a snapshot is appended through `fitness.record_snapshot` only when a value changed. A snapshot is an athlete reading, not a run, so it is not under the INV-8 confirmation gate; it is the same data `sync_fitness` writes today. If the spike says no, keep the manual prompt and drop the fitness chart from R8.4.3. |
| R8.4.2 | **"Building or holding?" — load trend** – ✅ **shipped (2026-10-09)** — exactly 1.10 and 0.90 read *holding* (ratios rounded to 2 dp first) | New service `training_trends.load_trend(db, *, as_of)` returns the last 7 days' km, the average week over the previous 28 days, their ratio, and the longest run in each window. Verdict, labelled a heuristic: **building** if the ratio is above 1.1, **holding** if it is 0.9–1.1, **easing** if it is below 0.9 (taper-aware: easing inside 3 weeks of a planned race reads "taper"). Thresholds are module constants with a why-comment. Endpoint `GET /api/training/trends` plus MCP tool `get_training_trends`, and a 4-week rolling-average line on the weekly Volume chart. |
| R8.4.3 | **"What's my form now?" — form trend** – ✅ **shipped (2026-10-09)** — m per beat chosen over pace-at-HR (same noise, keeps every steady run, barely moves with effort); verdict ±3% over 6 vs. 12 weeks (B20) | Same service, `form_trend`. Plots monthly **efficiency** (speed per heartbeat, m per beat, across steady runs: untagged or Easy/Long Run, ≥ 5 km, HR present, elapsed within 1.2× moving time — a heuristic, labelled), plus a rolling 90-day best 5k and 10k from R8.2 best efforts vs. the all-time best, plus the VO₂ max/threshold line from R8.4.1 snapshots. **Open question for the build session:** pace-at-fixed-HR band vs. m-per-beat — try both on the real archive and keep the one that reads honestly. |
| R8.4.4 | **"Am I ready for race X?" — readiness** – ✅ **shipped (2026-10-09)** — `race_advisor.race_readiness`, `GET /api/races/readiness`, in `get_race_block_context` (B20) | `race_advisor` already builds race-block context for the MCP prompt; extend that instead of starting a parallel service. For the next planned race: weeks to go; peak week and longest run in the block; long-run count over a distance-relative threshold (e.g. ≥ 28 km for a marathon); recent best efforts vs. target pace when `target_time_s` is set. Shown as a checklist with numbers, not a score. Same data on REST + `get_race_block_context`. |
| R8.4.5 | **Page layout** – ✅ **shipped (2026-10-09)** — `NowStrip.jsx` | New top strip "Now": three answer cards (Load · Form · Next race), each a verdict line + one small chart, stacked on mobile and in a 3-column row on desktop. Below it, the current page unchanged (tiles, Volume, Races/Records, Fitness/Predictions, Activities). Fitness/Predictions get "as of" freshness, and a sparkline once R8.4.1 has history. `vite build` clean, 0 console errors, desktop + 380 px pass. |

**Order:**
1. R8.4.1 spike first (minutes, decides R8.4.3's scope).
2. Then R8.4.2 → R8.4.3 → R8.4.4, backend + tests for each before any UI.
3. R8.4.5 last, consuming all three.

Commits `r8:` one per task. **Exit:** the three answers render from one endpoint each with tests on the threshold boundaries (exactly 1.1 is building? — decide and test it), taper inside 3 weeks, no-HR runs excluded, no planned race → readiness card hides.

---

## R9 — Public deals page for the run club *(scoped 2026-10-15 at the runner's request — R9.1–R9.4 and R9.6 built 2026-10-15; R9.5 code built, go-live human steps pending)*

*Share `anton.musasouled.com/deals` with the run club. Anyone with the link sees the shoes on sale ("Musa's picks"). Everything else stays behind the password, and signing in lands on Home exactly as today. This is Anton's first deliberately public data surface, so the security work ships **before** the link is shared, not alongside it. Grounded in a code read on 2026-10-15 of `middleware/auth.py`, `routers/session.py`, `services/sessions.py`, `services/rate_limit.py`, `routers/deals.py`, `models/schemas/deals.py`, `pages/Deals.jsx`, `DealDetailModal.jsx`, `AuthGate.jsx`, `vite.config.js` and `deploy/Caddyfile`.*

**Already in place (don't rebuild):** default-deny auth middleware with an exact-match `PUBLIC_PATHS` allowlist that covers every route including `/mcp`; an httpOnly + Secure + SameSite=Lax session cookie, hashed at rest, 14-day TTL; Origin-check CSRF on cookie-authenticated writes; timing-safe password compare; per-IP login (5/min) and auth-failure (10/min) limiters; credential-redacting logs; HSTS; a bundle with no secrets in it. The existing gate stays the boundary. R9 opens it by exactly one path.

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R9.1 | ✅ **Built 2026-10-15.** **Gate regression test + limiter cap** | A test that walks every registered route and asserts a logged-out request gets 401, except a pinned public allowlist. Cap the in-memory rate-limiter dicts. Detail in §R9.1. | Turns "everything else is gated" from a belief into a check that also catches future sessions adding a route. | — | Low |
| R9.2 | ✅ **Built 2026-10-15.** **Sign out everywhere** | One action that ends every browser session **and** every claude.ai OAuth token. Changing the password triggers it automatically on restart. Settings → Security card (the playbook is in `architecture.md` only, not shown in the app). Detail in §R9.2. | The leaked-password / lost-phone playbook. Today logout only ends the current device. | — | Low–Medium |
| R9.3 | ✅ **Built 2026-10-15.** **Public deals endpoint** | `GET /api/public/deals`: a field-allowlisted projection of active deals, rate-limited, the only new public path. Detail in §R9.3. | The current deal payload carries personal fields (`notes`, `target_price`, `size_fit`) that must never go public. | R9.1 | Low |
| R9.4 | ✅ **Built 2026-10-15.** **Public deals page ("Musa's picks")** | Logged-out `/deals` renders a read-only page with filters and a Sign-in link. Logged-in `/deals` is unchanged. Detail in §R9.4. | The thing the run club actually sees. | R9.3 | Low–Medium |
| R9.5 | 🟡 **Code built 2026-10-15; human go-live steps pending** (see §R9.5). **Edge hardening + go-live** | Security headers + noindex in Caddy, a global login-failure ceiling, passphrase rotation, a production smoke test. Detail in §R9.5. | More eyes on the login form, and a link that will get forwarded. | R9.1–R9.4 | Low |
| R9.6 | ✅ **Built 2026-10-15** (E20, architecture §11, CLAUDE.md §1 + INV-10). **Docs** | Decision entry, trust-model update, stale CLAUDE.md §1 line. Detail in §R9.6. | Standing rule. | R9.1–R9.5 | Low |

**Order within R9:** R9.1 → R9.2 (one session, backend-first) → R9.3 → R9.4 (one session) → R9.5 → R9.6. **The link is shared only after R9.5's exit check passes.** R9.2 is useful on its own and can ship first even if the public page waits.

### §R9 — Threat model: what changes when the link goes out

The host has been public since RA1 and bots already probe it. The link adds *attention* and a known URL: friendly but curious club members (some will open dev tools), whoever they forward it to, and the same bots. The named-bearer (Desktop, loopback) and OAuth connector paths are unchanged.

| Risk | Mitigation | Task |
|---|---|---|
| A non-public route answers a logged-out request (now, or after a future session adds one) | Route-coverage test with a pinned allowlist | R9.1 |
| Public payload leaks personal data: `ShoeResponse.notes`, `target_price` (personal "ping me at"), R6.3 `size_fit` (reveals your size), the watchlist, retailer `scraper_config` | Dedicated `PublicDeal` schema built from an explicit field list, plus a leak test | R9.3 |
| Public page mounts a component that calls an authed endpoint: every 401 burns the visitor's auth-failure bucket and fires `UNAUTHENTICATED_EVENT`. Or a write control (Archive deal, Bought it, Stop watching) leaks into the public view | Separate public component tree using only `usePublicDeals`. No `DealDetailModal` | R9.4 |
| Password guessing on a now-familiar login screen | Existing per-IP limiter + a global ceiling + passphrase rotation | R9.5 |
| Password leaks or a device is lost | Sign out everywhere (sessions + OAuth); automatic on password change | R9.2 |
| Load or abuse on the public endpoint; unbounded limiter memory (`KeyedRateLimiter`'s own docstring: "if this were ever exposed to an open network the unbounded dict would need capping") | Public per-IP limiter; `max_keys` cap on every keyed limiter | R9.1, R9.3 |
| A public GET triggers work (scrape, sync) | Endpoint is a plain read query; a test asserts no scrape/lock call | R9.3 |
| Clickjacking, referrer leakage, search indexing | Caddy headers, `X-Robots-Tag: noindex`, `robots.txt`, `rel="noopener noreferrer"` | R9.4, R9.5 |
| Republishing scraped prices to a group (not a security risk, worth knowing) | Kept low-key: noindex, small audience, every deal links to the retailer. Take a retailer down if one ever asks | R9.5 |

### §R9.1 — Gate regression test + limiter cap

- **`tests/test_public_surface.py`:** enumerate `app.routes` (API routes, plain routes, the `/mcp` mount, and the OAuth routes, which `tests/conftest.py` already enables via `ANTON_HOST_URL`). For each declared method except OPTIONS (which passes through by design), fill path params with dummy values, send a request with no credentials, and assert 401. The only exemptions are paths in `PUBLIC_PATHS`.
- **Pin `PUBLIC_PATHS` to a literal expected set in the same test.** Adding a public path then has to touch the test: deliberate friction that shows up in the PR diff.
- **Limiter cap:** `KeyedRateLimiter` gets `max_keys` (e.g. 10 000). When full, it evicts buckets that have refilled to capacity first. A full bucket is identical to a fresh one, so evicting it loses nothing; a currently throttled IP is never reset. Applies to all limiters (auth-failure, login, chat, the new public one).
- **Tests:** the route walk; `max_keys` stays bounded and a throttled IP stays throttled across evictions.
- **Exit:** green on today's code. This is a ratchet, not a fix. If it finds a hole, that's a correctness bug and gets fixed in this task.

### §R9.2 — Sign out everywhere

**Today:** `DELETE /api/auth/session` deletes only the session presenting the cookie. The password is `ANTON_LOGIN_PASSWORD` in `backend/.env`, and the same password gates `/oauth/login`. So someone who knows it can also connect *their own* claude.ai to Anton's MCP and hold OAuth tokens that survive a session wipe. "Everywhere" therefore means **all `sessions` rows + all OAuth access/refresh tokens + pending auth codes**. Named bearer tokens (Desktop, loopback) don't come from the password and stay untouched; they rotate via `ANTON_TOKENS` as today.

- **Service:** `sessions.revoke_all(db) -> int` and `oauth.revoke_all(db) -> int`, composed by one `sign_out_everywhere(db)` service that returns both counts and logs a WARNING with the counts and source IP.
- **Endpoint:** `POST /api/auth/sign-out-everywhere`. Cookie-authenticated, not in `PUBLIC_PATHS`; the middleware's Origin CSRF check applies automatically. It clears the caller's cookie too. The SPA then fires `UNAUTHENTICATED_EVENT`, which already wipes the offline caches and shows the login screen.
- **Automatic on password change:** at boot (lifespan, after migrations) compute a salted, slow fingerprint of `ANTON_LOGIN_PASSWORD` (`hashlib.scrypt`, stdlib, random salt) and compare it with `AppSettings["login_password_fingerprint"]`. On a mismatch, run `sign_out_everywhere`, store the new fingerprint, and log a WARNING. First boot with nothing stored: store it, don't purge. *Why scrypt and not SHA-256:* the DB is replicated to B2 by Litestream, and a plain hash of a passphrase sitting in a backup can be cracked offline.
- **Leaked-password playbook (lives in `architecture.md` only; deliberately not shown in the Settings card):** change `ANTON_LOGIN_PASSWORD` on the server, run `docker compose up -d --force-recreate` (not `restart`, which doesn't re-read `env_file`), sign in again, reconnect the claude.ai connector. Every other device and connector is already out.
- **CLI fallback:** `scripts/sign_out_everywhere.py` for use over SSH (phone lost and no other signed-in device).
- **Settings → Security card:** "Signed in on N devices · Claude connector: connected / not connected" (counts only, from `GET /api/auth/security`), and a destructive **Sign out everywhere** button behind a confirmation dialog (CLAUDE.md §7).
- **Not on MCP:** a deliberate exception to REST/MCP parity (CLAUDE.md §4.2). Auth administration isn't an AI-callable capability. Record it in `design_decisions.md`.
- **Tests:** a cookie valid before revoke gets 401 after; an OAuth token stops verifying; bearer tokens still work; the endpoint returns 401 logged-out and 403 cross-origin; fingerprint unchanged → no purge, changed → purge, first boot → no purge.
- **Known limit:** a device that is offline keeps showing its cached reads until it next reaches the server (then 401 → wipe). Same as RA2.2 today.
- **Decision (v1): the password stays in env.** The alternative is a hashed password in the DB with "change password" in Settings, which requires the current password. The env version means a stolen session can never change the password and lock you out; the cost is that changing it needs SSH. Revisit only if changing it from the phone becomes a felt need.

### §R9.3 — Public deals endpoint

- **`GET /api/public/deals`** in a new `routers/public.py` (prefix `/api/public`), added to `PUBLIC_PATHS` as that exact path. GET only, **no query parameters** (filters stay client-side, as on today's Deals page), so there's nothing to tune and nothing to abuse.
- **Service:** `deals.list_public_deals(db)`, a thin projection over the existing `list_deals(is_active=True)`. One computation, as in CLAUDE.md §6.
- **Schema `PublicDeal`, built field by field (never `from_attributes` on the ORM object):** `shoe_id`, `brand`, `model`, `shoe_type`, `colorway`, `image_url`, `current_price`, `msrp`, `savings_amount`, `savings_percent`, `sizes_available`, `in_stock`, `retailer_id`, `retailer_name`, `product_url`, `promo_codes` (code, description, discount), `detected_at`. Envelope: `{"deals": [...], "checked_at": <last successful scrape>}`.
- **Never in the payload:** `notes`, `target_price`, `size_fit`, `is_active`, anything from the watchlist, retailer `scraper_config` / platform internals, owned shoes, price history.
- **Rate limit:** a new `public_limiter` per IP (60/min, burst 60, env-tunable via `PUBLIC_RATE_LIMIT_*`) → 429 + Retry-After. Response header `Cache-Control: public, max-age=300`.
- **Tests:** the exact key set; a leak test that seeds a shoe with `notes="SECRET-NOTE"`, a `target_price` and a preferred size, then asserts none of them appear anywhere in the body; only active deals are returned; 429 after the burst; no scrape lock or orchestrator call; other methods are refused.
- **No new MCP tool:** `get_deals` already serves the owner.

### §R9.4 — Public deals page ("Musa's picks")

- **Routing:** `AuthGate` gets one public-route branch. Logged-out at `/deals` → `<PublicDeals />` in a standalone shell (no nav, no chat drawer, no scrape button, no Watching section). Logged-in at `/deals` → today's Deals page, unchanged. Logged-out anywhere else → `LoginView`, unchanged. After signing in from the public page → navigate to `/` (Home).
- **Data:** only `usePublicDeals` (`api.js` `publicApi.deals` → `useApi.js`). The page must never mount a component that calls an authed hook. Brand, retailer, type and size options are derived from the payload, not from `/shoes` or `/retailers`.
- **Components:** reuse `ShoeProductCard` if it is display-only (verify it calls no hooks). Deal detail goes in a new read-only `PublicDealSheet`: image, price, retail price, savings, sizes, promo codes, "View at retailer". Not `DealDetailModal`, which loads authed price history and carries Archive / Bought it / Stop watching.
- **Filters:** size (most prominent on mobile, since every runner's size differs), brand, retailer, type, min savings, sort.
- **Copy:** header **"Musa's picks"**, then one line: *"Shoes I'd actually buy, on sale now at Canadian retailers. Prices checked {relative checked_at}."* A small "Sign in" link in the footer. No emoji (R7.1). Outbound links use `target="_blank" rel="noopener noreferrer"`.
- **PWA note:** visitors also get the service worker (it registers for everyone). That's fine, since the bundle and this payload are both public. "Add to Home Screen" from `/deals` would open at `start_url: '/'` → login. Acceptable for v1.
- **Exit:** a logged-out visit makes exactly two API calls (`/api/auth/session` probe + `/api/public/deals`), with 0 401s and 0 console errors in the network tab. Desktop + ~380 px pass. Signing in from the page lands on Home. Logged-in `/deals` is pixel-identical to today.

### §R9.5 — Edge hardening + go-live

- **Caddy headers (whole site):** `X-Content-Type-Options nosniff`, `Referrer-Policy strict-origin-when-cross-origin`, `X-Frame-Options DENY`, `X-Robots-Tag "noindex, nofollow"`, a minimal `Permissions-Policy`. CSP first as **`Content-Security-Policy-Report-Only`** (`default-src 'self'; img-src 'self' https: data:; font-src https://fonts.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; connect-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; frame-ancestors 'none'`); switch to enforcing after a clean week. Before enforcing (2026-10-15): the inline theme-boot script moved to `public/theme-boot.js`, and connect-src allows the Google Fonts hosts because the service worker fetches them itself. Add `public/robots.txt` with `Disallow: /`.
- **Global login-failure ceiling** across all IPs (e.g. 50 failures/hour), on top of the per-IP limiter, so a distributed guess can't fan out. Trade-off: an attacker could lock the *login form* for up to an hour. Existing sessions (14-day), the Desktop bearer and the connector keep working, so it's acceptable. Confirm the number at build time.
- **Status 2026-10-15:** the code is built (Caddyfile headers + CSP report-only, `robots.txt`, `/.well-known/oauth-protected-resource` added to the repo `@backend` matcher, global ceiling `LOGIN_GLOBAL_FAILURE_LIMIT_PER_HOUR`=50). The Caddyfile has **not** been validated (no `caddy`/docker locally). Everything marked *Human* below is still to do, in this order: validate and reconcile the server Caddyfile; deploy backend + `dist/`; rotate the password with `docker compose up -d --force-recreate`; reconnect the connector; smoke test; then share.
- **Human step, before sharing:** rotate `ANTON_LOGIN_PASSWORD` to a long passphrase (5+ random words). This also exercises R9.2's automatic purge end to end.
- **Reconcile Caddy and `PUBLIC_PATHS`:** `/.well-known/oauth-protected-resource` is in `PUBLIC_PATHS` but not in the repo Caddyfile's `@backend` matcher (it would fall through to the SPA). The connector works in production, so check whether the server's Caddyfile differs from the repo and make them match.
- **Deploy both halves** (backend + `dist/`), then smoke-test from a logged-out private window on cellular.
- **Exit:** headers present (`curl -I`); logged-out `/deals` works; every other page shows login; `curl https://anton.musasouled.com/api/owned-shoes/` → 401; `/api/public/deals` returns no personal fields.

### §R9.6 — Docs

- `design_decisions.md`: new entry covering the first public data surface; the field-allowlist schema; the route-coverage test as the ratchet; sign-out scope (sessions + OAuth, not bearers) and the MCP-parity exception; password stays in env.
- `architecture.md` §11 trust model: add the public tier and the leaked-password playbook (kept in the doc, not the app).
- `CLAUDE.md` §1 still says "no auth by explicit deferral", stale since RA1. Correct it.
- `project_state.md` and the changelog, as usual.

**Not in scope:** accounts for club members, per-member size preferences or alerts, a public watchlist ("Watching"), public price history (could come later as a projection if asked), analytics or visitor tracking, affiliate links.

**Exit (R9 as a whole):** (1) logged-out `/deals` shows active deals with no personal fields (leak test green); (2) every other route answers 401 to a logged-out request (route-coverage test green, spot-checked in production); (3) Sign out everywhere logs out a second device and the claude.ai connector, and changing the password does the same after a recreate; (4) logged in, Home and `/deals` are unchanged; (5) suite + CI green, `vite build` clean, desktop + ~380 px pass.

---

## R10 — Training dashboard on claude.ai, now also in the app *(scoped + scheduled 2026-10-20 at the runner's request; R10.4 brought both pages into the Training page the same day)*

*Raised 2026-10-20 in a Cowork session: the runner wants a shareable training dashboard outside the app, built as a claude.ai Dashboard artifact that reads Anton live through the `anton` MCP connector. Page 1 first, page 2 next. Grounded in live calls to `get_training_summary`, `get_training_trends`, `get_personal_bests`, `get_planned_races` and `get_rotation_insights` the same day.*

**Ground rule (CLAUDE.md §2.1, "correct numbers, once"):** the dashboard is a *projection*. Every number comes from an Anton MCP tool answer; the artifact only reshapes it for charts (rows, sorting, unit formatting). If a page needs a number Anton does not serve, it goes into an Anton service + REST + MCP tool first (§4.2 parity) — never computed in the artifact.

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R10.1 | **Dashboard page 1: Load · Form · Records** | One page combining (1) **volume & load**: weekly km for the last 52 weeks with the 4-week rolling line, last-7-days vs prior-28-day ratio and the building/holding/easing verdict, longest-run comparison; (2) **fitness & form**: monthly m-per-beat line (months with too few steady runs shown as gaps), the slipping/steady/improving verdict, COROS VO₂ max + threshold pace step lines; (3) **records**: race PBs, best efforts (with the run each segment came from), recent-vs-all-time 5k/10k. Live queries: `get_training_summary(period="weekly")`, `get_training_trends`, `get_personal_bests`. No Anton code change. | A glanceable, shareable view of the three questions R8.4 answers in-app, without opening Anton. | R8.4 (trends tool), R8.2 (best efforts) — both shipped | Low |
| R10.2 | **Dashboard page 2: race-block retrospective** – ✅ **backend built (2026-10-20)**: `race_advisor.block_comparison` on readiness' `block_window`, `GET /api/races/blocks`, MCP `get_block_comparison` (B25); dashboard page added, live after deploy | Compare marathon blocks side by side (TCS Toronto 2025-10-19, Ottawa 2026-05-24, Beneva 2026-10-11; halves optional): the 16 weeks before each race — weekly km curve aligned on race week, peak week, long runs ≥ 28 km, average easy pace/HR, and result vs target. **Backend first:** new `race_advisor.block_comparison(db, *, weeks=16)` (or a sibling in `training_trends`) + `GET /api/races/blocks` + MCP tool `get_block_comparison`, tests on alignment (race week = week 0), a race with no linked run, and overlapping blocks. Then the dashboard page over that one tool. **Reverses R8.4's "not chosen: block-vs-block comparison"** — the runner asked for it on 2026-10-20. | Planning the next build from what actually preceded each result. | R10.3 (race list must be right first) | Medium (backend + tests, then page) |
| R10.3 | **Race data fixes found while scoping** – ✅ **code built (2026-10-20)**: Beneva was a **DNF at ~14 km**, not a bad data link → new `dnf` race status (B24); 8 non-race runs (runner-confirmed) untagged in production 2026-10-20; merged PR #86 | (a) **Beneva Marathon result reads 3059 s** (51 min) for a 42.2 km race — `planned_races.result_time_s` or the linked `activity_id` 1024 is wrong; find which and fix through the race edit/link path. (b) **Synthetic past races include non-races** — `races.list_races` surfaces Race-tagged runs such as "Race Week: Easy run to get legs moving" (12.3 km, 8982 s) and "First Solo Run since marathon"; check their tags (likely archive tagging) and fix the data, or tighten the rule if the tags are right. Correctness bugs (CLAUDE.md §11 exception). | The race board and R10.2 read these lists; a 51-min marathon or a shakeout listed as a race would make both look wrong. | none | Low |
| R10.4 | **Race blocks in the app** – ✅ **built 2026-10-20** (branch `r10-blocks-in-app`) | The claude.ai dashboard's page 2 is now also a Training-page section; the claude.ai artifact stays as the shareable view. New section id `blocks` (label "Race blocks"), full-width, not a card section, added to the hand-matched `TRAINING_SECTIONS` in `services/settings.py` and `lib/trainingLayout.js`, default slot after `races`; saved layouts get it appended at the end through `normalizeLayout` (test `test_old_seven_id_layout_appends_blocks_visible`). Data: `racesApi.blocks(raceClass)` → `GET /api/races/blocks`, hook `useRaceBlocks`, keys `raceBlocks(cls)` = `['races','blocks',cls]` and `raceBlocksAll()`; race writes are covered by the `['races']` prefix, run writes (activity edit/reassign/promote, log run, delete run, COROS confirm) invalidate `raceBlocksAll()` next to readiness. `components/training/RaceBlocksCard.jsx`: Marathon/Half/10k switch remembered per device (localStorage `anton.raceBlocks.class`, E24); takeaway line built from the response only; Recharts weekly-km-by-offset lines, one per block in `--chart-1..6`, the in-progress block dashed (desktop: collision-aware end labels via `<Customized>`; ≤ 640 px: a legend; tooltip shows km and runs per block); side-by-side table, newest first, deep-linking to the race's run, DNF in the warning colour, last four columns hidden below 520 px; heuristic footnote (+ a half-class note that long-run counts run high inside marathon builds); loading, empty and error states. **No backend change** — every number is served by `block_comparison` (B25); the card only formats and picks rows. **Page-1 gap closed:** `FitnessCard` gains a threshold-pace step line (`ThresholdSparkline`) from `trends.form.fitness[].threshold_pace_s_per_km`, reversed axis (faster reads up), shown as M:SS/km. **Page-1 audit (R6):** NowStrip, VolumeChart, RecordsCard and FitnessCard cover dashboard page 1; the one difference is the Volume chart's default range (see R10.5). | The runner can read both dashboard pages inside Anton, on the phone, without the claude.ai connector. | R10.2 backend | Low–Medium |
| R10.5 | **Follow-ups** – ✅ **built 2026-10-20** (branch `r10-5-followups`) | The runner decided all three. (a) **Volume chart default range → 1y:** the Training page's shared range (Volume chart, summary, activities list) now opens on the last 365 days, the 1y preset, matching the dashboard's 52 weeks; 90d stays one tap away. (b) **Chart draws the newest 6 blocks:** `MAX_CHART_BLOCKS = 6` matches the six `--chart-*` tokens, so colours never repeat; older blocks stay in the table with a hollow dot, and a note reads "Chart shows the 6 newest of N blocks; the table lists all." One shared `chartSlot` helper keeps the chart and table colours in step. `ChartLegend` takes an optional per-item `key` (two truncated labels collided). (c) **Toronto activity 423 is not a race** (runner, 2026-10-20): it stays tagged Long Run; no data change. | Closes R10.4's loose ends. | R10.4 | Low |
| R10.6 | **Training page in tabs** – ✅ **built 2026-10-20** (branch `training-tabs`) | The page was too busy as one scroll. It is now three tabs held in `?tab=`: **Overview** (the dashboard's page 1: Now, Volume with its own range, then Fitness and Records), **Races** (Planned races and Predictions, then Race blocks) and **Activities** (run list with its own range and filters). Each tab is a page-local component, so its queries run only while shown. Date-range state was extracted to `hooks/useDateRange.js` + `DateRangeControls`. Customize (E16) is removed from the frontend. E25. | The runner reads training the way the dashboard groups it, on the phone. | R10.4 | Low–Medium |
| R10.7 | **Retire the training-layout backend** – ✅ **built 2026-10-20** (branch `r10-7-layout-cleanup`) | Delete `training_layout` from `GET /api/preferences`, `PUT /api/preferences/training-layout`, `TRAINING_SECTIONS` / `get_training_layout` in `services/settings.py`, and their tests; nothing calls them since E25. Leave the stored `app_settings` row (harmless) or drop it in the same change. | Removes dead surface (CLAUDE.md §11 shim expiry). | R10.6 | Low |

**Order:** R10.1 now (no backend work). Then R10.3 (small, correctness). Then R10.2 backend + tests → page 2. Then R10.4 (in-app Race blocks + threshold line, no backend). R10.5 closes the follow-ups; R10.6 splits the page into tabs; R10.7 is the backend cleanup. Commits `r10:`, one per task.

**Exit:** page 1 renders from live Anton tool calls with no numbers typed into the page; page 2 compares at least the three marathon blocks from `get_block_comparison`; Beneva shows its real time. R10.4: the Training page shows the same blocks (Marathon/Half/10k) and the threshold-pace line.

---

## R11 — Race readiness v2: evidence, not a checklist *(scoped 2026-10-20 at the runner's request — R11.1–R11.7 all built 2026-10-20; R11.6 on branch `r11-6-splits`, B28)*

*Fills the open note in the 2026-10-20 changelog ("the runner has further ideas for the Readiness section… no roadmap row"). Source: an external readiness spec, triaged with the runner on 2026-10-20 into build / nice-to-have / decline; the triage outcome is at the end of this section. Grounded in a read of `services/race_advisor.py` (`race_readiness`, `block_window`, `block_comparison`) the same day.*

**Already shipped — don't rebuild:**
- Readiness checklist (R8.4.4, B20): next race, weeks to go, exact target pace, peak week, longest run, long-run count, recent key effort vs target pace. REST `GET /api/races/readiness`, MCP `get_race_block_context.readiness`, the Readiness section on the Races tab.
- Block comparison (R10.2/R10.4, B25): blocks aligned on race week (offset 0), Marathon/Half/10k switch, in-progress block dashed (never shown as zero), DNF shown, deep links to each race's run.
- Load trend with a taper verdict inside 3 weeks of a race (R8.4.2); form trend (R8.4.3); best efforts inside runs (R8.2); COROS fitness snapshots (R8.4.1).

**What v2 adds:** the four questions the spec asks — *how likely is my target, on what evidence, what are the gaps, what can I still do* — answered as separate, sourced dimensions, compared with your own past builds rather than fixed thresholds.

**Rules:**
- **No single ready/not-ready score.** Dimensions stay separate. The one prediction allowed is a finish-time **range** with its evidence grade (R11.7), only when the evidence supports one and only if its backtest passes. That is Anton's first prediction of its own, so it gets a `design_decisions.md` entry (extends B20).
- **"No data" is never "not met".** A rule is `not_met` only when there is evidence and it falls short.
- **Extend `race_advisor`, don't fork it.** Every number is computed there; REST + MCP parity through the existing readiness payload (CLAUDE.md §2/§4).
- **Your own blocks are the yardstick.** Prefer "vs. your past builds at the same week" to new fixed thresholds. Any new threshold is a module constant with a why-comment, labelled a heuristic.
- **Storage:** only the R11.4 exclusion fields (R11.5 reuses the existing `planned_shoe_id`; no new column). Backtests and comparisons are computed live, never stored (INV-7).
- Mobile-first: 380 px pass on the Races tab for every UI task.

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R11.1 | **Evidence + drill-down on every checklist item** *(✅ built)* | New `no_data` status; each item carries its period and the activities behind its number; tapping an item lists those runs. Detail in §R11.1. | Answers "what evidence, and how current?" (spec Q2). Fixes a real honesty bug: today no recent effort reads `not_met`. | R8.4.4 | Low–Medium |
| R11.2 | **"At this point in past builds"** *(✅ built)* | Each block number compared with your past blocks of the same class *at the same week offset*, with each past race's result (incl. DNF) beside it. Detail in §R11.2. | The individualized comparison the spec asks for, from data `block_comparison` already computes. | R10.2 | Low |
| R11.3 | **Consistency + taper items** *(✅ built)* | Weeks with running, runs per week, gaps ≥ 7 days; inside the final 3 weeks, each week as % of block peak and days since the last long run / key effort. Descriptive, no pass/fail. Detail in §R11.3. | Two of the spec's six dimensions, cheap from the block's runs. | R11.2 (taper reads against past builds) | Low |
| R11.4 | **Exclude an activity from analysis** *(✅ built (B26; migration `f5a6b7c8d9e0`))* | Per-activity flag + reason (GPS error, wrong sport, duplicate, …) that removes a run from derived analytics only — never from mileage. Detail in §R11.4. | The spec's "data the app interpreted incorrectly". Needed before R11.7 so one bad file can't move an estimate. | T6 activity edit | Low–Medium |
| R11.5 | **Race-shoe readiness** *(✅ built (reuses `planned_shoe_id`))* | Pick the race shoe on a planned race; readiness shows its mileage at race day (R6.2 forecast) and how it's been used in the block. Detail in §R11.5. | The one readiness dimension only Anton can answer — shoes × runs. | R6.2 forecast | Low–Medium |
| R11.6 | **Fast finish in long runs** *(✅ built (B28; migration `b9c0d1e2f3a4`) — the spike showed segments can't answer it, so the runner reopened R5.4.3)* *(spike-gated)* | Did the block's long runs finish faster? Spike whether R8.2 segment offsets answer it; if not, this is the named question that reopens R5.4.3 splits. Detail in §R11.6. | Marathon durability — what shorter-race fitness can't show. | R8.2; possibly R5.4.3 | Medium |
| R11.7 | **Finish-time range + evidence grade** *(✅ built (B27) — the runner chose to build after the spike recommended against it)* *(spike-gated)* | Backtest candidate estimators against past races first; build a range with an evidence grade and a "not enough evidence" state only if the backtest error is acceptable to the runner. Detail in §R11.7. | Spec Q1 — "how likely is my target?" — answered honestly, with its own historical error shown. | R11.1–R11.4, R11.6 | Medium–High |

**Order:** R11.1 → R11.2 → R11.3 (all over existing data) → R11.4 (before the estimate) → R11.5 → R11.6 spike → R11.7 spike, then build if it passes. Backend + tests before UI in every task. Commits `r11:`, one per task.

### §R11.1 — Evidence + drill-down

- **New status `no_data`** in `race_advisor.STATUSES`. Today `key_effort` is `not_met` when there is no effort in the window; that becomes `no_data` ("no half effort recorded since …"). `not_met` only when an effort exists and is slower than target pace. Audit every item for the same distinction. The status string is hand-matched: update `RaceReadiness.jsx` and the `race_block_advisor` prompt text with it.
- **`ChecklistItem` gains `period_from`/`period_to` and `evidence`** — a list of `{activity_id, run_date, distance_km, segment}`:
  - longest run → that run; long runs → the list; peak week → that week's runs; key effort → its source run (segment flag kept).
  - The data is already on `RaceReadiness` (`longest_run`, `long_runs`, `recent_efforts`); this puts it on the item it supports.
- **Age:** the key effort carries `age_days` so the UI can fade older evidence. No recency weighting in this task (that belongs to R11.7, if anywhere).
- **UI:** tapping an item expands to its runs, each linking to `/activities/:id`.
- **Tests:** no effort → `no_data`; slower effort → `not_met`; evidence ids match the numbers; no race → section hidden, unchanged.

### §R11.2 — "At this point in past builds"

- In `race_readiness`, for the next race's class, take past **completed or DNF** blocks from `block_comparison` and read each one *up to the same offset* as today (e.g. week −6): cumulative km, long runs so far, longest run so far, peak week so far.
- **Cumulative-to-offset, not whole-block totals** — a block six weeks in compared with finished blocks would read as failure (the spec's in-progress rule).
- Output a `past_builds` list: race name, date, status, result time vs target, and the values at the same offset. **No ranking, no "more km = better" wording** — results sit next to the numbers and the runner draws the conclusion.
- Reuse `_build_block`'s week rows; no new endpoint (added to the readiness payload, so MCP gets it too).
- **UI:** a compact "At this point in past builds" table under the checklist. Hidden when the class has no past blocks.
- **Tests:** offset alignment; a past block with no runs at that offset; DNF included; no past blocks → empty list.

### §R11.3 — Consistency + taper

- **Consistency** (info items, block so far): weeks with ≥ 1 run / weeks elapsed; median runs per week; gaps of ≥ 7 days between runs, listed with dates. The gap list is where R11.4's reasons and the parked training notes would explain an interruption.
- **Taper** (info, only inside the final 3 weeks — reuse the taper window constant from `training_trends.load_trend`, don't redefine it): each of the last 3 weeks' km as % of the block's peak week; days since the last long run; days since the last key-distance effort. Shown next to the same numbers from past builds (R11.2), **no target percentages**.
- **Tests:** a gap spanning a week boundary; taper hidden at 22 days out, shown at 21; a one-week block.

### §R11.4 — Exclude an activity from analysis

- `activities.exclude_from_analysis` (bool, default false) + `exclude_reason` (controlled list: `gps_error`, `wrong_sport`, `duplicate`, `treadmill_calibration`, `other`, plus optional text). Additive E4 migration.
- **Respected by derived analytics only:** readiness, block comparison, load/form trends, best efforts and Best-effort records (R8.2 already anticipated "allow excluding an activity from records"). Decide at build whether Race PBs honour it; default: no — a race result is an official record.
- **Never touches the mileage ledger or volume totals** (INV-1/INV-2). Shoe mileage and weekly km stay as logged; fixing a wrong distance is still an activity edit.
- Set from the activity detail page through the existing `PATCH /api/activities/{id}` (no MCP write tool, same as other activity edits today). Excluded runs show a small "excluded from analysis: reason" line.
- **Tests:** an excluded run drops out of each consumer above; shoe mileage and weekly totals unchanged; reason vocabulary validated (422).

### §R11.5 — Race-shoe readiness

- **Built without a new column:** `planned_races.planned_shoe_id` already existed (nullable, race-form picker, nulled by `rotation.delete_owned_shoe`), so it is reused; the planned `race_shoe_id` + migration were dropped. *(Original plan: a new nullable FK → `owned_shoes`.)*
- **Readiness item `race_shoe`:**
  - projected mileage on race day from the R6.2 forecast vs the shoe's own `mileage_limit` — `not_met` only if it will pass its limit before race day (the runner's own limit, not a new threshold);
  - info: runs and km in it during the block, longest run in it, last run in it.
  - No race shoe set → `n/a` with "pick a race shoe".
- `get_planned_races` and the readiness payload carry it.
- **Tests:** forecast crossing the limit before race day; shoe deleted → field nulls; no shoe → `n/a`.

### §R11.6 — Fast finish in long runs *(spike-gated)*

**Built:** 2026-10-20 (B28, `design_decisions.md`), branch `r11-6-splits`. The spike found segments can't show a fast finish, so the runner reopened R5.4.3 (§R5.4.3 below) and built per-km splits. Readiness now carries `long_run_finishes` per long run in the block (first vs second half moving pace, last full km vs run average, second half vs target pace) and a `fast_finish` info item ("N of M long runs had a faster second half"; `no_data` when no long run has splits; unscanned runs say "not scanned yet"). REST and MCP parity; the Races tab has a "Long-run finishes" tile opening a table. The spike's findings were moved into B28; the spike doc is deleted (`git show c8902f0:docs/spike_r11_6_fast_finish.md`).

- **Question:** in this block's long runs, did the runner hold or lift pace late — the marathon-durability signal the spec asks for?
- **Spike (no product code):** `activity_best_efforts` stores the fastest segment per distance per activity with `start_offset_m`. For each long run in the last three marathon blocks: does the best 5k/10k segment sit in the final third, and how does its pace compare with the run's average and with target pace? Judge on real runs whether that reads honestly — it only finds the *fastest* segment, not "the last 10 km".
- **If it reads honestly:** info item `fast_finish` — long runs with a late fast segment, the segment's pace vs target pace, each with its run.
- **If not:** stop. This is the named question that reopens R5.4.3 (splits); move R5.4.3 out of Parked & gated and scope it there rather than approximating here.

### §R11.7 — Finish-time range + evidence grade *(spike-gated)*

**Built:** 2026-10-20 (B27, `design_decisions.md`), branch `r11-7-finish-estimate`. The spike recommended not building; the runner read it and chose to build. `services/finish_estimate.py` implements the a-fast method (fastest Riegel equivalent, k 1.06, 10k/half race results and best efforts in the 8 weeks before block end), the range from the live backtest's largest past error, and the strong/moderate/thin grade. Backend and tests are committed (`ed14038`); the UI is committed (`79a8fff`). Changelog: the R11.7 entry. The spike doc was deleted; its findings are in B27 and readable at `git show fa14554:docs/spike_r11_7_finish_estimate.md`.

- **Spike first — backtest.** `race_readiness` already takes `as_of`. For each past completed race (marathons and halves), compute candidate estimators as of the day before and compare with the actual result:
  - (a) equivalency from the best recent race or effort (Riegel, exponent stated);
  - (b) recent key-distance effort pace;
  - (c) a durability adjustment from long-run evidence (R11.6 if it shipped).
  - COROS `race_predictions` has history only since 2026-10-09, so it can't be backtested; show it as a separate, labelled source.
  - DNF races are excluded from scoring (`_readiness_race` skips `dnf`; say so in the report). The sample is tiny — report n with every error.
- **The runner decides on the spike report.** If the error is too large, ship nothing and record that decision; the R11.1–R11.6 dimensions stand on their own.
- **If built:** an `estimate` on the readiness payload:
  - `low`/`high` finish time and the target time's position in it;
  - source rows (method, run, date) behind it;
  - an evidence grade (`strong` / `moderate` / `thin`) with the reasons in words (e.g. "no half-distance effort in 8 weeks", "2 of 3 long runs"); the range widens as evidence thins;
  - a "not enough evidence" state naming what's missing — no range shown;
  - the backtest error beside it, computed live, not stored.
- **Decision entry** in `design_decisions.md` before the build (first Anton-made prediction; how it differs from a score).
- **Tests:** thin evidence → no range; a past race's estimate is reproducible from `as_of`; DNF excluded from backtest scoring.

**Triage of the 2026-10-20 spec (for reference).** Built above: everything in the table. Nice-to-haves went to Parked & gated with triggers: % of peak toggle on the block chart, picking individual blocks to compare, a target-time what-if, a race-day rehearsal checklist (fueling / pacing / course), dated training notes (illness, travel), and COROS recovery/HRV in readiness. Declined: a smoothed-trend toggle (about 16 weekly points don't need it), a daily soreness/mood/fatigue log (the niggle-log habit test applies), rolling load ratios (COROS already shows them), a taper-volume or race-day-assumption what-if (a model on top of an estimate — false precision), and an estimate-history view (R11.7's live backtest covers calibration).

**Exit (R11 as a whole):** every readiness item shows its period and source runs, and "no data" never reads as "not met"; the next race's numbers sit beside past builds at the same week; consistency and taper render with no pass/fail thresholds; an excluded run drops out of analytics with mileage unchanged; the race shoe's race-day mileage shows; R11.6 and R11.7 each end in either a shipped item or a recorded decision. **Met 2026-10-20: R11.6 shipped (B28) and R11.7 shipped (B27).** Suite + CI green, `vite build` clean, desktop + 380 px pass.

---

## R12 — Lean COROS sync from Claude *(scoped 2026-10-31 at the runner's request)*

The COROS poller already does the heavy work (fetch, dedup, suggest); what remains is the conversation round trip. Target shape: one lean fetch (table + rotation) → the runner replies → one `confirm_pending_coros_runs` batch call → a server-computed summary. INV-8 (human confirmation gate) is unchanged.

**Executing contract:** `docs/COROS_SYNC_LEAN_PLAN.md` (T0–T8; T7 inbox button optional).

---

## Parked & gated — one list *(added and confirmed by the runner 2026-10-10)*

*Everything deliberately not built, in one place. Each item names why it's parked and the trigger that would reopen it. Detail stays in the item's own section; this list is the index. When a trigger fires, move the item back into its milestone.*

| Item | Status | Why parked | Reopen when |
|------|--------|-----------|-------------|
| R5.4.2 external weather lookup (Open-Meteo) | ⏸ parked 2026-10-10 | Heat analysis on the 215 archive rows showed no effect once fitness is controlled (§R5.4.2) | A hot-weather sample shows a felt or measured effect; then spike + decision entry (first outbound per-run call) |
| R5.5 phase 2 — heat-adjusted efficiency | ⏸ parked 2026-10-10 | Same result; needs the lookup above | Same trigger |
| ~~R5.4.3 splits / laps / HR~~ | ✅ built 2026-10-20 (B28) | Stored derived data (B19-style exception) + COROS FIT download budget, with no question asking for it yet | A named question, e.g. "do I negative-split long runs?" or "HR drift on steady runs" |
| R5.5 phase 2 — negative splits / HR drift | 🟡 negative splits covered by R11.6 (B28); HR drift unblocked, not built | `activity_splits` now holds per-km HR and moving time; HR drift needs a view over it | You want aerobic decoupling on steady runs; then build a read-only view over `activity_splits` |
| R5.5 phase 2 — by-place views + runner-named places | ⏸ gated | Location now exists (R5.4.1); no felt need for place views yet | You'd look at running by place (home loops / travel / race venues); then cluster start points into runner-named places, not reverse geocoding |
| Son of Anton saves an owned shoe (R5.3 follow-up) | ⏸ not scoped | Claude can draft a purchase but not save it; saving is in the app | You want to add a shoe through chat; needs a new confirm-gated write tool (R7.2 card) |
| Injury context — niggle log | ⏸ parked 2026-10-10 | "Not needed for now"; value depends on logging within a day (§R5.5 note) | A month of jotting niggles in run descriptions shows the habit holds |
| COROS recovery / HRV / resting-HR ingestion | ⏸ deferred (R5.7); re-checked 2026-10-20 for R11 | A readiness view now exists (R11), but COROS already shows these trends and nothing in R11 would change a decision with them | A readiness decision you'd make differently with recovery data alongside it; zero manual logging needed |
| R11 nice-to-haves: % of peak toggle on the block chart; picking individual blocks to compare | 🟡 triaged 2026-10-20 | Useful only when blocks have very different peaks; the class switch covers most comparisons | You find yourself comparing two specific builds and the chart gets in the way |
| R11 nice-to-have: target-time what-if | 🟡 triaged 2026-10-20 | Cheap (target pace recomputes), but changing the race's target already does it | You want to try targets without editing the race |
| R11 nice-to-have: race-day rehearsal checklist (fueling, pacing plan, course) | 🟡 triaged 2026-10-20 | Real marathon risk, but no data source; a per-race static list is enough | A race where fueling or pacing went wrong for want of a rehearsal |
| R11 nice-to-have: dated training notes (illness, travel, weather) | 🟡 triaged 2026-10-20 | R11.3 lists the gaps; R11.4 handles bad data. Illness notes are health data (keep out of MCP default outputs) | Gaps in R11.3 keep needing an explanation you can't see; same habit test as the niggle log |
| R5.7 deferrals: auto-confirm, Partner-API webhooks, cycling | ⏸ deferred (R5.7) | Auto-confirm would break the confirmation gate (INV-8); webhooks/cycling have no need | Auto-confirm only with an explicit decision; the others on a felt need |
| R6.4 "new run waiting" push (R3.5 revisit) | ⏸ measured, not built | Step 0: 1 run, 0.1 d lag, 0 waiting | Re-run the Step 0 query after a few weeks of use; build if runs sit for days |
| R5.1 native mobile client | ⏸ parked 2026-09-04 | The PWA covers it; push was the native win and is gated above | A native-only need (on-device HealthKit / COROS read) |
| Offline write-queue (split from RA2.2) | ⏸ gated | Replaying confirmation-gated writes against stale state breaks INV-1 / INV-9 (E11) | A felt "needed to log off-grid and couldn't" |
| Remote MCP for other clients (e.g. ChatGPT) | ⏸ deferred (R5.2 note) | No second client in use | A second MCP client is actually wanted |
| RA3 "not in scope" items: GHCR images, auto-rollback, staging | ⏸ deferred until felt | On-server build is fine at this size | The on-server Playwright build gets slow or memory-tight |
| `.webmanifest` content-type in Caddy | optional cleanup | Harmless — browsers parse the manifest anyway | Any Caddyfile touch |

**Declined (closed, kept for reference):** R4.2 agent scheduling & event delivery and R4.3 semi-automated COROS cadence (both 2026-08-29, absorbed by the mobile connector).

---

## Dependency Spine (the short version)

```
R1 (loose ends) ─▶ R2 (security · schema · platform — complete 2026-07-08)
                        │
                        ▼
                  RA1 Remote backend (auth v2 + always-on host + cutover)   ← executes R5.2
                        │            RA1.0 D0/spikes → (RA1.1 ∥ RA1.2) → RA1.3+RA1.4 → RA1.5 → RA1.6
                        ├▶ R3 agents (parked) ─▶ R4 automation (parked) ─▶ RA2 remote clients ─▶ R5.1 Mobile
                        └▶ (RA2 can also precede R3/R4 if the pocket UI matters sooner)
R2.7 Training Depth (complete): T1 → T2 → T3 · T1 → T4/T5/T6 · T6 → T7 · T2 → T8
R2.5 Observability ─▶ R4.1 Scheduling ─▶ R4.2/4.5
R3.5 Channel ─▶ everything proactive
R2.7 T5 (fitness metrics) ─▶ R3.4 (fitness resource) ─▶ R3.6 (race advisor richer)
```

Three rules fall out of the spine: **nothing unattended before R2.1** (satisfied), **nothing scheduled before R2.5** (satisfied), and **nothing internet-exposed before RA1's auth v2 + TLS land together** — a public bind with the single shared cleartext token is a regression, not an intermediate state. Everything else is negotiable in order.

---

*Maintenance note: this file is a living artifact (see R5.6). When an item ships, move its row into `project_state.md` §3 and record any decision it embodied in `design_decisions.md`. When priorities change, re-order here and say why in the changelog entry — the roadmap's history is part of the roadmap.*
