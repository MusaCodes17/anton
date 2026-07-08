# Anton — Product Roadmap

**Generated:** 2026-07-04. **Last updated:** 2026-07-07 (R2.1 marked done; R2.7 Training & Activity Depth added from user feature requests).
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
| R2.2 | **Schema authority resolution** | Alembic becomes the sole schema source: `create_all` demoted to test fixtures; `legacy_migrations/` archived; live DB + `.bak*` files relocated out of the tree (e.g. `~/anton-data/`) with a dated-backup convention; `DATABASE_URL` already supports the move. | Ends the "model edit without migration silently diverges" trap and the five-backups-next-to-source ambiguity. Prerequisite hygiene for every future migration. | R1.1 (docs committed) | Medium |
| R2.3 | **Indexed read paths over the canonical table** | Swap `unified_activities` internals from whole-table Python to SQL date-range/shoe/pagination queries (the seam guarantees zero caller changes); extract `services/watchlist.py` from the fat router the same way. | Home's <200 ms budget vs. a growing decade of history; watchlist extraction is also what unlocks MCP watchlist parity (R3.4). The canonical table was built to make this possible — cash it in. | R1.4 (eager-loading conventions set) | Medium |
| R2.4 | **Shoe-type controlled vocabulary** | Promote `shoe_type` from free strings to a small backend-owned vocabulary (lookup table or enum) used by both domains and *served* to the frontend (deleting `lib/shoeTypes.js` as an independent copy). | The cross-domain bridge is the most load-bearing string set in the system; a typo currently fails silently. Three copies exist today. | none | Low–Medium |
| R2.5 | **Scrape observability** | Persist scrape runs/attempts (per retailer: started, finished, product count, error) written by the orchestrator; surface per-retailer health + trend in Settings → Sync & Scraping. | "Is Altitude quietly broken?" becomes a query instead of log archaeology. The substrate R4.1 (scheduling) and R4.5 (watchdog) require. Forces the documented decision on the single-process lock. | none | Medium |
| R2.6 | **Server-side conversation & memory persistence** | Move Son of Anton conversations (and checkpoint-prompt state) from localStorage into the backend (tables + endpoints), keeping the client stateless-per-request contract. | Device-bound memory contradicts the API-first multi-client principle; agents (R3) need shared context; quota-trimming currently discards history silently. Scheduled-to-change in design_decisions C8. | R2.1 (chat endpoints stop being anonymous) | Medium |
| R2.7 | **Training & Activity Depth** | A self-contained milestone adding richer per-activity data, smarter records, athlete-level fitness metrics, and activity editing. Eight sub-items (T1–T8) ordered internally by dependency — schema foundation first, then services, then UI. See §R2.7 below for the full breakdown. | Turns the Training tab from a volume tracker into a genuine training log; makes the records card trustworthy; surfaces COROS athlete metrics the platform already fetches but discards. | R2.2 (migration hygiene before schema changes); internal sub-item dependencies noted in §R2.7 | Medium–High (write `TRAINING_DEPTH_PLAN.md` before executing) |

**Order within R2:** 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7. (Security first; schema hygiene before anything that adds tables — 2.5, 2.6, and 2.7 all add columns/tables and should be born as clean migrations. R2.7 can run in parallel with 2.3–2.6 once 2.2 is done.)

---

## §R2.7 — Training & Activity Depth (detailed breakdown)

*Eight sub-items from user feature requests (2026-07-07). `TRAINING_DEPTH_PLAN.md` (repo root) is the executing contract — this milestone touches the canonical `Activity` table and the PB algorithm, both of which require the E4 migration discipline.*

**Internal dependency order: T1 → T2 → T3 (schema foundation), then T4/T5/T6 in parallel, then T7, then T8.**

**Progress:** ✅ **Session 1 done (2026-07-07, Session F): T1 · T2 · T3** — tag vocabulary + 4 `activities` columns (migration `e5f6a7b8c9d0`), COROS field population, PB eligibility fix. Remaining: T4/T5/T6 (Session 2), T7/T8 (Session 3). See changelog 2026-07-07 and project_state §3.

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

**COROS API coverage:** Before planning the sync implementation, verify which COROS Open-API endpoint exposes these fields — include a discovery step in `TRAINING_DEPTH_PLAN.md`. If the server-side `coros_client` path cannot access them (credential restriction), extend the `sync_coros_runs` Claude Desktop agent prompt to fetch and confirm them alongside runs.

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

## R3 — AI Capabilities

*The redesign built the surfaces; R3 populates them. Every agent obeys C9: prepare and propose, the runner disposes.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R3.1 | **Weekly Rotation Summary Agent** | An MCP prompt (sibling of `sync_coros_runs`) + on-demand trigger that composes the week: km vs last week, per-shoe usage, pipeline movement, checkpoints crossed, notable runs — rendered as a digest the runner reads Monday. Backlog item with its surfaces (Home, Training) already built. | The first *proactive* value from the AI layer, built almost entirely from existing tools (`get_training_summary`, `retirement_pipeline`, `get_shoe_runs`). Proves the agent pattern cheaply. R2.7 T1 activity tags make "notable runs" (`Race`, `Tempo`) identifiable. | none hard; R2.6 makes digests persistent; R2.7 T1 enriches "notable runs" | Medium |
| R3.2 | **Deal Alert Agent** | Detection + digest for deal *events*: new qualified deal on a tracked shoe, price-drop on an active deal, replacement-deal appearing for a pipeline shoe. On-demand/"since last check" first (persisted high-water mark); push delivery arrives with R4.2. | The deals domain's whole purpose is timely opportunity — today it requires opening the app. Backlog item; Home top-deals module is its surface. | R2.5 helps (event source); delivery beyond in-app needs R3.5 | Medium |
| R3.3 | **Shoe review pipeline maturation** | Grow `draft_shoe_review` (MCP sampling) into a workflow: retirement → prompt to review → draft from the notes journal → runner edits → stored on the shoe (and exportable). | The notes journal exists to feed this; retirement is its natural trigger; it's the payoff of the mileage-anchored journaling discipline. | R1.3 pattern (detail-page work); storage column | Low–Medium |
| R3.4 | **MCP watchlist parity + resource expansion** | Expose the watchlist through MCP (tool + resource) once R2.3 extracts the service; add `training://fitness` resource (R2.7 T5 athlete metrics) for chat pre-priming alongside `training://summary`. | Son of Anton currently can't answer "what am I watching and what's the best price ever?" — the only major read surface missing from the AI layer. | R2.3; R2.7 T5 for fitness resource | Low |
| R3.5 | **Notification channel (Email MCP or equivalent)** | One outbound channel for agent output — the explored Email MCP, or the simplest reliable alternative (e.g. a digest endpoint the phone reads). Decide once, use for R3.1/R3.2/R4.5. | Agents that can only speak when spoken to aren't agents. Channel choice is a one-time decision every proactive feature reuses. | R2.1 (an authenticated system shouldn't email from an open one) | Medium |
| R3.6 | **Race-block training advisor** | A prompt-encoded advisor over existing data: weeks-to-race (planned_races), recent volume/paces (training summary), rotation state, VO2 Max + threshold pace (R2.7 T5) — producing block-level observations ("9 weeks out, volume trailing your Ottawa build; threshold pace suggests 3:43/km target pace"). Advisory text only; no plan-generation pretensions. | Highest-value reasoning use of data already collected; zero new schema. The runner's actual use case (sub-2:37 target). R2.7 T5 makes this considerably richer. | R3.1 (shares digest machinery); R2.7 T5 (fitness metrics) | Medium |

**Order within R3:** 3.1 → 3.4 → 3.3 → 3.2 → 3.5 → 3.6.

---

## R4 — Automation

*Remove the human trigger where — and only where — the human isn't the point. Confirmation gates on writes remain non-negotiable.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R4.1 | **Scheduled scraping** | Nightly (or N-hourly) scrape runs via a real design: persisted job state, DB-level or documented single-process coordination replacing the bare in-memory lock, per-retailer staggering, failure recording into R2.5's tables. This is where APScheduler earns re-admission (R1.6). | Deal data is only as good as its freshness; manual triggering is the platform's biggest remaining chore. | R2.5 (observability), R1.6 decision; R2.1 before exposing any trigger surface | Medium–High |
| R4.2 | **Agent scheduling & event delivery** | Weekly summary auto-runs Monday morning; deal alerts fire on new-deal events from scheduled scrapes; both deliver via R3.5's channel. | Turns R3's on-demand agents into ambient value — Anton starts *telling* the runner things. | R3.1, R3.2, R3.5, R4.1 | Medium |
| R4.3 | **Semi-automated COROS cadence** | Within the Claude-Desktop-mediated constraint (design_decisions C6): a "runs pending sync" nudge (Home strip already shows last-sync) + one-tap launch of the `sync_coros_runs` flow. Full automation is *not* possible while COROS OAuth is desktop-managed — design to the constraint, don't fight it. | Sync friction is the main data-freshness gap on the training side. | R3.5 (nudge channel) | Low–Medium |
| R4.4 | **Coupon Hunting Agent** | Periodic promo-code discovery beyond the current homepage regex: agent-driven checks of retailer promo pages, validated codes landing in `promo_codes` (source=`scraped`; manual still wins). Explored-and-deferred wishlist item. | Stacking a promo on a qualified deal is real money; currently ad-hoc. | R4.1 (scheduler), scraper heuristics | Medium |
| R4.5 | **Scraper watchdog** | Trend rules over R2.5 data: "retailer X has returned 0 products for 3 runs" → alert via R3.5. | Silent scraper death is the current failure mode (visible only in logs); the deal feed degrades invisibly. | R2.5, R3.5, R4.1 | Low |

**Order within R4:** 4.1 → 4.5 → 4.2 → 4.3 → 4.4.

---

## R5 — Long-Term Vision

*Anton as a durable personal platform: reachable anywhere, ingesting everything relevant, reasoning across a decade of data. Everything here deserves its own plan doc before code.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R5.1 | **Native mobile client** | The long-anticipated app: Home as launch screen (built to budget for this), log-run + sync-nudge + deal alerts as the core loop. Precede with a typed/generated API contract (OpenAPI client) — the moment a second consumer exists, hand-matched string contracts stop scaling (design_decisions A5's named trigger). | The platform's stated destination; every API-first discipline since Phase 1 was bought for this. | R2.1 (hard gate), R2.6, R3.5; contract-generation spike | High |
| R5.2 | **Remote access story** | Decide how Anton is reached off-LAN: private overlay (Tailscale-style) vs hosted. Revisit the deferred remote-MCP-for-ChatGPT transport here, not before. | Mobile off-WiFi and any third-party MCP client both need this answered; it's a security-architecture decision, not a feature. | R2.1, R2.2 | Medium–High |
| R5.3 | **Purchase-loop closure** | Optional provenance from deal → owned shoe: "I bought this" on a deal creates/links an owned shoe with purchase price pre-filled. Must respect B1 (wanting ≠ owning): an *optional recorded event*, never a forced workflow or FK entanglement. | Closes the platform's narrative loop (watch → buy → run → retire → replace) and feeds real cost/km from day one. | R2.4 (shared vocabulary) | Medium |
| R5.4 | **Richer ingestion** | Candidates, each its own decision: per-run FIT-file detail (COROS MCP already exposes FIT downloads) for splits/HR curves; periodic Strava re-exports folded in via the existing idempotent importer; weather-at-run enrichment. Gate each on a question it answers, not on data availability. R2.7 T1 columns provide natural landing spots for split data. | The canonical `activities` table is deliberately a superset schema — it can absorb richer data without restructuring. | R2.3; per-source spikes | High (aggregate) |
| R5.5 | **Longitudinal analytics** | The decade-scale questions: shoe-model performance correlations (pace/HR by shoe across years), wear-rate curves by type, injury-pattern context (the recurring left-leg history) annotated against volume spikes. R2.7 activity tags make this richer ("race pace trend over 3 years", "interval-session frequency vs PB trajectory"). Read-only analytics over `activities` — no new writes. | This is why eight years of history was imported and made canonical: Anton's endgame is *insight*, not logging. | R2.3, R2.7 T1, R5.4 helps | High |
| R5.6 | **Documentation as infrastructure, permanently** | The Phase-2 (implementation) workflow from `documentation_creation.md`: milestone plans executed by cheaper coding agents, with `project_state.md` / `roadmap.md` / `design_decisions.md` updated continuously as living artifacts. | The meta-bet of this whole program: sessions that start with accurate context outperform sessions that start with archaeology. | R1.1 | Ongoing |

**Order within R5:** 5.2 and the R5.1 contract spike can start once R2 lands; 5.3 anytime after R2.4; 5.4/5.5 follow data needs, not a schedule.

---

## Dependency Spine (the short version)

```
R1 (loose ends) ─▶ R2.1 Security ─▶ R2.2 Schema ─▶ R2.3 Indexed reads ─┬▶ R3 agents ─▶ R4 automation ─▶ R5.1 Mobile
                                        │                                └▶ R5.2 Remote access
                                        └▶ R2.7 Training Depth
                                              T1 → T2 → T3
                                              T1 → T4 / T5 / T6
                                              T6 → T7
                                              T2 → T8
R2.5 Observability ─▶ R4.1 Scheduling ─▶ R4.2/4.5
R3.5 Channel ─▶ everything proactive
R2.7 T5 (fitness metrics) ─▶ R3.4 (fitness resource) ─▶ R3.6 (race advisor richer)
```

Two rules fall out of the spine: **nothing unattended before R2.1**, and **nothing scheduled before R2.5**. Everything else is negotiable in order.

---

*Maintenance note: this file is a living artifact (see R5.6). When an item ships, move its row into `project_state.md` §3 and record any decision it embodied in `design_decisions.md`. When priorities change, re-order here and say why in the changelog entry — the roadmap's history is part of the roadmap.*
