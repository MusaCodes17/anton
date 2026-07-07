# Anton — Session Changelog

**Last Updated:** 2026-07-07
**Status / current focus:** see `docs/project_state.md` (the perishable snapshot). This file is the append-only session log — the authoritative record of *what happened*; the `docs/` suite is the reference material.

---

## 🧹 R1 debt sweep + replacement-deals sizes — Phase 2 Session B — 2026-07-07

**[CHANGED] First implementation session after the documentation program. Closed out all remaining R1 loose ends (R1.3–R1.6): proxy-trap guards, four debt-sweep moves, the APScheduler decision, and the last missing field on the replacement-deals card. Seven `r1:` commits, one per task. Suite 64 → 67.**

- **[CHANGED] R1.4 — ShoeRun proxy traps guarded.** Every run-list seam that reads the `ShoeRun` property proxies (`distance_km`, `run_date`, `source`, `avg_pace`, `avg_hr`, `notes`, `coros_activity_id`) already joined `Activity` but never populated the relationship, so proxy access still fired a per-row lazy load (N+1). Added `.options(contains_eager(ShoeRun.activity))` to all five seams — the four `mcp_server.py` queries (`get_shoe_runs` tool, `draft_shoe_review`, shoe-detail resource, run-history resource) and the `owned_shoes` `/runs` endpoint. Added a `WARNING` comment on the model documenting the lazy-load + `.filter()` hazards. Audited: no surviving `.filter()` on proxied attributes. *(refactor.md H4 step one; tech_debt 5.3 note.)*
- **[CHANGED] R1.5a — Task D done.** `_attach_computed_fields` (owned-shoe response shaping: image match, lifetime stats, cost/km) moved from `routers/owned_shoes.py` to public `rotation.attach_computed_fields` — the last router→router import (`coros_sync` → `owned_shoes`) is gone. Six call sites + `coros_sync` repointed; the dead `CHECKPOINT_INTERVAL_KM` re-export dropped (the constant already lives in `rotation`). *(tech_debt 6.3.)*
- **[REMOVED] R1.5b — `scraper_manager.py` shim deleted.** The pure re-export shim's five consumers (`routers/scraping`, `routers/shoes`, `mcp_server`, `scrape_runner`, `scrapers/__init__`) now import `ScrapeOrchestrator` / `lock` / `registry` directly; the misleading `ScraperManager` alias is retired so the real boundaries are visible. **D7 → Superseded** (design_decisions); tech_debt 5.4/6.5 struck.
- **[ADDED] R1.5c — pure `app/utils/pace.py`.** `seconds_to_pace` / `pace_to_seconds` were implemented three times (rotation, coros_client, and inline in the `ShoeRun.avg_pace` proxy — a layer violation). Now one implementation in a dependency-free module; `rotation` re-exports both names (callers unaffected), coros_client and the model proxy import directly. Unified on `round()` (coros previously truncated with `int()`; its input is already integer seconds/km so behavior is unchanged). *(tech_debt 5.5 struck.)*
- **[CHANGED] R1.5d — chat model catalog single-sourced.** `routers/chat.py` hard-coded the catalog while `chat_service` routed by name prefix (`gpt-*`/`gemini-*`/else). New `chat_service.MODELS` (id, label, description, provider) + `PROVIDERS` metadata + `get_models()` is the one source; `_get_provider` resolves provider by id lookup (no prefix matching, unknown → Anthropic); `/providers` groups `get_models()` and layers on key availability — response shape verified identical. *(tech_debt 5.7 struck.)*
- **[REMOVED] R1.6 — APScheduler dropped.** Declared in `requirements.txt`, imported nowhere; removed. A scheduling note in `scrapers/lock.py` records that scheduled scraping (roadmap R4.1) needs DB-level coordination replacing the in-memory lock before a scheduler returns. Verified: uninstalled from the venv, suite still green, app imports clean. **E5 → Superseded**; tech_debt 1.7 struck.
- **[ADDED] R1.3 — replacement-deals card: size availability.** R1.3's substance (replacing the June "Coming soon" placeholder with a live section) already shipped in PR #9; only the size field the spec calls for was missing. Added `sizes_available` to `GET /owned-shoes/{id}/replacement-deals` and rendered it on `ReplacementDealCard` (guarded — shows only for a non-empty size list). New `test_replacement_deals.py` (3 tests) pins the endpoint's list projection: worst-discount-first, same-model / other-type / inactive / out-of-stock exclusions, the sizes field, and the untyped-shoe empty response.
- **Verified:** backend suite **67 passing** (was 64; +3 replacement-deals tests). `vite build` clean. No schema change — `sizes_available` was already a `Deal` column, so no migration. **Visual-pass caveat:** the interactive desktop/~380 px console pass for R1.3 was *not* run live — ports 8000/5173 were held by the user's own dev servers and the running backend predates the new field and hangs on the endpoint; the frontend change is additive, null-guarded, and build-verified. Recommend an eyeball on a typed shoe with matching in-stock deals when convenient.

---

## 🏁 Documentation completion — R1.1 committed, invariants, skills library, vocab table — 2026-07-06

**[DOCS] The documentation program is committed and its review backlog (§8 steps 2–4) is closed. No application code changed.**

- **[ADDED] R1.1 shipped:** the entire suite (`docs/`, `refactoring/`, `CLAUDE.md`, `documentation_creation.md`, the `claude.md → docs/changelog.md` rename) committed as `docs: complete Phase 1 documentation program`. Verified first: `backend/.gitignore` (`*.db`) + root `.gitignore` (`*.db.bak*`) exclude the live DB and all seven backups — no `.gitignore` change needed.
- **[ADDED] `CLAUDE.md` §14 — Invariants:** the checkable list (INV-1…INV-8), one line each: what must hold → owning code path → covering test (or an explicit "no test / documentation-only" note). Test claims verified against the suite first-hand (e.g. `test_delete_run_keeps_strava_archive` covers INV-4; the ledger round-trip covers INV-1). `ai_context.md` §8 repointed: a lead-in cites §14 as canonical and the five invariant items carry surgical `INV-n` citations — the third "don't break these" list the review warned about (§4.3) now cannot form.
- **[ADDED] `.claude/skills/` implemented — all 13 skill files** per `docs/skills_library.md`, in its specified order (S13 → S01 → S03/S04 → S05/S06/S07 → the rest). Six-section structure, ≤ ~120 lines each, cite-don't-restate. Addendum A4 honored: S07 carries the `sync_coros_runs` step list + external-contract summary with a "the prompt source wins" disclaimer. S05 points at the Retailer Status table's new home (architecture §10). S11 makes "exactly one uvicorn worker" explicit (review §5). One-line index added to `CLAUDE.md` §3.
- **[ADDED] `shoe_type` vocabulary table** (review Addendum A2, completing the reconciliation session's inline enumeration): Value/Meaning table in `domain_model.md` §4.3, marked as-of 2026-07-06 / canonical until R2.4; §7.1 glossary row repointed at it; one sentence added to `design_decisions.md` B3 naming where the list lives.
- **[CHANGED] Bookkeeping:** review §8 steps 2–4 struck with pointers here; roadmap R1.1 row marked done and moved to project_state §3; project_state refreshed (snapshot note, §1/§2/§3/§10, §11 re-ordered — R1.4 now first); ai_context §9 item 1 and §12 skills line updated to reflect committed/implemented state.
- **Noted, not re-done:** session-prompt Tasks 4 (two CLAUDE.md §6 trap lines) and 5 (roadmap "watched shoe") were already executed by the same-day reconciliation session — verified present/clean first-hand.
- **Verified:** no application code touched; suite expected unchanged at **64** (run recorded by the runner at commit time). Committed as `docs: documentation completion — invariants, skills library, vocab table`.

---

## 📚 Documentation program complete — final review + docs reconciliation — 2026-07-06

**[DOCS] All prompts of `documentation_creation.md` are done. The final review (`docs/documentation_review.md` + same-day addendum) audited the suite; this session executed its §8.1 reconciliation backlog. No code changed.**
- **MSRP ripple fixed** across the suite (the 2026-07-06 MSRP change had landed after most docs were written): `domain_model.md` §4.1 rewritten to the B9-v2 rule (`price < msrp`, savings vs MSRP, no-MSRP → no deal) with the old rule kept as a historical note; §2.1/§4.11/§7.1 glossary updated (new **msrp** entry; **target price** demoted); `architecture.md` §5 (shoes/deals rows), §6 qualification invariant, and the §12 pipeline diagram updated; `CLAUDE.md` §9 and `design_decisions.md` B13 now say "qualifying-savings snapshot (MSRP-based since B9-v2)".
- **refactor.md / tech_debt.md re-stamped** to the current tree (`models.py` 18,858 B · suite 64 · `d4e5f6a7b8c9`): rotation-path findings (C1/C2/H2/H3/H4) stand; **H1/P1-4 narrowed** (`test_deals.py` pins the MSRP rules; retirement/orphan/promo + HTTP layer still open); **L2 and tech_debt §9.5 struck** — resolved differently by the MSRP change; **§9.7 flipped** Verify → Resolved.
- **Changelog cleaned up (roadmap R1.2)**: header retitled to "Anton — Session Changelog"; the stale pre-Phase-5 reference tail (old schema with data-bearing `shoe_runs`, target_price deal semantics, retired `/scrape/test/*` endpoints) **amputated** and replaced with a pointer into `docs/` — after first **relocating the Retailer Status table to `architecture.md` §10** (it is S05's required context); the Project Commands table corrected to reality (only `/project:migrate` exists).
- **`claude.md` ghost sweep**: every remaining reference to the deleted root file (architecture §3 tree/§3 note/§14.8/§16.8–.9, design_decisions header/E3/Superseded table, strava_backfill row) now points at `docs/changelog.md` or `CLAUDE.md` as appropriate.
- **Count-drift fixes + anti-drift rule**: 61→64 tests and 4→5 migrations corrected everywhere; henceforth **live counts are authoritative in exactly two places** (this file's newest entry + `project_state.md` §2) and the **authoritative migration list lives only in `architecture.md` §5** — other docs cite, don't count. Backup files are no longer counted in prose ("dated `.bak*` restore points").
- **project_state.md refreshed** to 2026-07-06 (doc program complete; MSRP decision recorded in §3/§9; §7 now defers to tech_debt as ranked authority; §11 re-ordered). **ai_context.md §11 staleness register cleared.**
- **Addendum findings applied**: `shoe_type` vocabulary enumerated in `domain_model.md` §7.1 (8 values, as-of-dated, pending R2.4); two new CLAUDE.md §6 traps (`_effective_moving_s` private import; hand-matched router↔`api.js`/SSE string contracts); stray "watched shoe" → "tracked shoe" in roadmap R3.2.
- **Roadmap**: R1.2 marked done; R1.1 narrowed to "commit the batch." **Next: commit `docs/` + `refactoring/` + `CLAUDE.md` + `documentation_creation.md` as one batch (R1.1)** — until then all of this is one `git clean` from gone. Then the review backlog: INVARIANTS section in CLAUDE.md → skills implementation (S13 + S01 first).

---

## 🆕 MSRP drives deals — replace target_price in all deal math — 2026-07-06

**[CHANGED] A deal is now any retailer price *below the shoe's MSRP*; savings % is measured against MSRP. `target_price` is demoted to an optional personal threshold that no longer affects qualification or savings.**
- **Qualification** (`orchestrator.scrape_retailer_for_shoe`): the old rule (retailer marking down from
  its own compare-at price AND price ≤ target_price) is replaced by a single test — `price < shoe.msrp`.
  The retailer's compare-at/original price is no longer consulted. A shoe with no MSRP can't produce
  deals (nothing to measure against). "On sale" now means "below list price."
- **Savings math** (`deal_store.upsert_deal`): `savings_amount = msrp - price`,
  `savings_percent = (msrp - price)/msrp*100`. Refresh-on-rescrape now triggers on a scraped-price move
  OR a recomputed-savings change (i.e. an MSRP edit "sticks"). Returns `False` (no deal) when msrp unset.
- **Schema / migration** `d4e5f6a7b8c9_msrp_drives_deals`: `shoes.target_price` and `deals.target_price`
  relaxed to nullable (batch mode, reversible). `Deal.target_price` kept as a reference snapshot only.
  Backup `shoe_deals.db.bak-msrp-drives-deals` taken first.
- **One-off data recompute** on the live DB (backed up): existing active deals re-scored against MSRP;
  deals at/above MSRP (or with no MSRP) deactivated. Net: 113 → 112 active deals (only Alphafly 3 @ $375
  = MSRP fell out). Reconciled: 0 active deals remain with `price ≥ msrp`. Prior one-off populated MSRP
  on all 45 remaining active shoes so none is now un-dealable.
- **API/MCP**: `add_shoe` reordered to `(brand, model, msrp=None, target_price=None)` with MSRP documented
  as the deal driver; deal dicts (`_deal_to_dict`, dashboard) now surface `msrp`. Schemas made
  `target_price` optional (`ShoeBase`, `DealBase`, `WatchlistItem`). `export.py` seed-gen emits msrp and
  skips a null target.
- **Frontend**: `ShoeForm` makes MSRP the required, deal-driving field (hint "a sale is any price below
  this") and target optional; `PriceChart` gains a dashed **MSRP (sale below)** reference line;
  target-price displays null-guarded in `DealDetailModal`, `WatchlistRow` ("Set" when unset), and
  `Shoes` price-history subtitle (MSRP shown first).
- **Verified**: pytest **64 passing** (+3 new `test_deals.py` pinning MSRP savings, MSRP-edit refresh,
  and no-MSRP→no-deal); `vite build` clean; live-DB smoke of `/api/watchlist`, `/api/deals`, `/api/home`,
  `/api/dashboard/best-deals` all 200 with MSRP-based savings (e.g. $95 vs $190 MSRP → 50%).

---

## 🆕 Anton redesign Phase 5 — canonical `activities` table (§3 v2) — 2026-07-04

**[CHANGED] The two run stores collapsed into one canonical `activities` table; `shoe_runs` is now a pure attribution row.**
- New `Activity` model (`models.py`) — superset of the old `strava_activities` columns + a `source`
  discriminator (`strava`|`coros`|`manual`) + `coros_activity_id`. Every physical run (Strava export,
  COROS sync, manual log) is one Activity row. `StravaActivity` model + table **removed**.
- `ShoeRun` rewritten to attribution only: `{id, activity_id (FK, unique), owned_shoe_id, created_at}`.
  Read-only proxy properties (`distance_km`, `run_date`, `source`, `avg_pace`, `avg_hr`, `notes`,
  `coros_activity_id`) pull from the joined activity so `ShoeRunResponse` and every reader keep the
  **identical response shape** — no frontend/MCP consumer changes.
- Migration `alembic/versions/c3d4e5f6a7b8_canonical_activities.py` (reversible): migrates
  `strava_activities` → `activities` (source='strava'); linked `shoe_runs` become attribution for the
  matching strava activity (stamping its `coros_activity_id`); unlinked post-export runs mint fresh
  activities; rebuilds `shoe_runs`; drops `strava_activities`. Downgrade reconstitutes both old tables.
  **`current_mileage` counters untouched** — storage restructured, totals unchanged.
- Write path (`rotation.log_run`) now creates an Activity then the attribution row; `delete_run`
  removes the attribution + decrements mileage, deleting the activity too **except** source='strava'
  (frozen archive preserved). `coros.confirm_run`/`is_already_logged` dedup on
  `activities.coros_activity_id`. `activities._build` (the union seam) simplifies to one join — no more
  dedup-by-link. `strava_import` upserts into `activities`; `strava /status` + MCP readers repoint.
- **[REMOVED]** `strava_backfill.py` + its CLI + test — the two-store reconciliation it performed is
  exactly what this migration makes permanent (Strava export is frozen; no new cross-store dups).
- Verified on the live DB: pre/post reconciliation exact (698 runs · 8028.02 km · 667 attributed ·
  0 per-shoe mileage drift; 933 activities), `downgrade -1` round-trips clean, full suite **61 passed**
  (new `tests/test_activities_model.py`), `/training` + `/shoes/:id` + `/` render identical numbers,
  0 console errors. Clean pre-migration backup kept at `backend/shoe_deals.db.bak-pre-activities`.

---

## 🆕 Anton redesign Phase 5 — true app mark for Anton — 2026-07-04

**[ADDED] A real logo mark: a forward-leaning "A" monogram, replacing the placeholder diamond.**
- New `frontend/src/components/layout/BrandMark.jsx` — an italic "A" (apex shifted right of its
  base so the letter leans into a stride) with the crossbar drawn as a motion line that overshoots
  the right leg into a trail. Strokes use `currentColor`, so callers pick the colour.
- Wired into `Layout.jsx` `Brand` (green `bg-primary` tile, `text-background` strokes — same
  negative-space treatment as before, real glyph now) for both the desktop sidebar and mobile top
  bar. Legible at 28px.
- `public/favicon.svg` replaced (was a pulse-line) with the matching mark: green rounded tile +
  dark "A". `index.html` already points at it.
- Nav active/inactive **diamond dots left as-is** — they're a functional indicator motif, not the
  logo. Verified desktop + ~380px, `vite build` clean, 0 console errors.

---

## 🆕 Anton redesign Phase 5 — `/shoes` lifecycle reframe — 2026-07-04

**[ADDED] Retirement pipeline + group-by-type on `/shoes`; shared server-side pipeline computation.**
- New `rotation.retirement_pipeline(db, threshold=0.75)` + `rotation.active_deal_counts_by_type(db)`
  in `app/services/rotation.py` — the single authoritative "which active shoes are ≥75% of their
  `mileage_limit`, worst-first, and how many replacement deals exist" computation. Replacement deals
  are the heuristic §4 bridge: active deals on a tracked `Shoe` of the same `shoe_type` (no FK).
- **[REFACTORED]** `home._shoe_alerts` is now a thin projection over `retirement_pipeline` (dropped
  its duplicated query + local `ALERT_THRESHOLD`), so the Home shoe-alerts module and the Shoes page
  can never disagree about thresholds/ordering/counts.
- New thin endpoint `GET /api/owned-shoes/rotation-overview` → `{threshold, pipeline[]}` where each
  entry is `{owned_shoe_id, pct, current_mileage, mileage_limit, replacement_deals}`. Deliberately
  id-keyed/lightweight — the page already has full shoe rows from `GET /owned-shoes` and groups them
  by type client-side (trivial); the endpoint supplies only the server-computed pieces (API-first §2.1).
- Frontend (`pages/MyShoes.jsx`): active rotation now renders **grouped by shoe type** (groups ordered
  like the type filter, `Uncategorized` last; header = label · count · total km) with a **Retirement
  pipeline** band above it (`RetirementPipeline`/`PipelineRow`, worst-first, red/warning mileage bar,
  pct badge, "N replacement deals" button deep-linking to `/deals`; pipeline shoes still appear in
  their type group — the band is an attention surface, not a move). `useRotationOverview` hook +
  `ownedShoesApi.rotationOverview`. "Add a shoe" is now a full-width button below the groups.
- Tests: `tests/test_rotation_overview.py` (6) — threshold + boundary (exactly 75% included),
  worst-first ordering, replacement-deal counting (type-scoped, active-only, case-insensitive),
  untyped→0, empty pipeline. Full suite 69 passed. Desktop (grouped) + ~380px (stacked) pass, 0
  console errors.

---

## 🆕 Anton redesign Phase 4 — Home rebuilt as an attention surface — 2026-07-03

**[ADDED] `GET /api/home` + a rebuilt Home page (`/`) — four attention modules in one round trip.**
- New `app/services/home.py` (`home_summary(db, today)`) aggregates all four §4 modules; thin
  router `app/routers/home.py` (`GET /api/home`, ~110ms locally). API-first: every number computed
  server-side.
  - **Training pulse**: this-week vs last-week km (Monday-anchored, computed off the unioned run
    feed so an empty week reads 0), + newest run (distance, pace, HR, shoe, source).
  - **Shoe alerts**: active owned shoes at/over 75% of `mileage_limit`, worst-first, each with a
    replacement-deal count (active deals on a tracked `Shoe` of the same `shoe_type` — heuristic,
    no FK). Empty = "Rotation healthy" shown small + proud.
  - **Top deals**: 3 deepest active discounts, biggest savings % first.
  - **Activity strip**: last COROS sync (`app_settings.last_coros_sync_at`), last scrape
    (`max(retailers.last_scraped_at)`), newest active deal detected.
- Frontend: `pages/Home.jsx` (Dashboard convention — inline sub-components), `useHome` hook,
  `homeApi.summary`. Every module deep-links into its tab (`/training`, `/deals?deal=id`, `/shoes`).
- **[REMOVED]** old `pages/Dashboard.jsx` + `components/TrainingVolumeCard.jsx` (+ now-dead
  `useRecentDeals`/`useBestDeals` hooks). `useDashboardStats` kept — still used by Layout + Settings.
- Tests: `tests/test_home.py` (10) — week-over-week math, empty-week-reads-0, last-run selection,
  75% threshold + worst-first ordering + replacement-deal counting, top-deals ranking/cap, strip.
  Full suite 63 passed. Desktop (no-scroll) + ~380px passes clean, 0 console errors.

---

## Project Commands

Only one project command exists on disk: `/project:migrate` (run a DB migration — pattern + existing scripts). A former table here listed four others that were never written; their intent is absorbed by the skills library design (`docs/skills_library.md` — e.g. `add-retailer` → S05). Corrected 2026-07-06.

---

## 🆕 Shoe detail page, purchase price/cost-per-km, notes journal, mileage checkpoints — 2026-06-24

**[ADDED] A full `/my-shoes/:id` detail page, replacing the old quick-view dialog as the permanent home for run history.**
- New route `frontend/src/pages/ShoeDetail.jsx`. Card click target ("Details" button or the
  image/name header) now navigates here instead of opening a dialog; the old `ShoeDetailDialog`
  in `MyShoes.jsx` was removed entirely (run history moved into the new page, nothing duplicated).
- Layout: image/brand/model/nickname header with status badge and purchase-price line → stats row
  (mileage bar, total runs, lifetime avg pace/HR when present) → a **Replacement Deals** placeholder
  card (explicitly empty — "Coming soon" badge, no logic, just holding the layout slot for later) →
  **Shoe Notes Journal** → **Run History**.
- **[ADDED]** `purchase_price` (nullable float) on `owned_shoes` (migration
  `backend/migrate_add_shoe_notes.py`, same idempotent-`ALTER TABLE` pattern as prior owned_shoes
  migrations). Exposed in `OwnedShoeBase`/`Update` and as computed `cost_per_km` on
  `OwnedShoeResponse` (`purchase_price / current_mileage`, rounded 2dp, only when both are set) —
  computed server-side in `_attach_computed_fields` so the REST API, MCP tools, and frontend all
  show the identical number instead of each recomputing it. `OwnedShoeForm` gained a "Purchase
  price ($)" field.
- **[ADDED]** "Adjust mileage" action on the detail page — a small two-step dialog (enter value →
  explicit confirm showing old/new) that PUTs `current_mileage` directly via the existing
  `OwnedShoeUpdate` endpoint. Deliberately not a new endpoint — `current_mileage` was already
  updatable via `PUT /owned-shoes/{id}`; this just gives it dedicated UI with a confirmation step
  since it silently overrides accumulated run mileage rather than logging a run.

**[ADDED] Shoe Notes Journal — replaces the old single free-text `owned_shoes.notes` column.**
- New table `shoe_notes` (`id`, `owned_shoe_id`, `body`, `mileage_at_note`, `triggered_by`
  ["manual"|"checkpoint"], `created_at`) — a timestamped, mileage-anchored history instead of one
  overwritable text blob. `migrate_add_shoe_notes.py` migrates any existing `owned_shoes.notes`
  text into a `triggered_by="manual"` entry (mileage_at_note = current_mileage at migration time),
  then drops the old column. Ran live: 2 existing notes migrated cleanly.
- Endpoints (`routers/owned_shoes.py`): `GET/POST /api/owned-shoes/{id}/notes`,
  `DELETE /api/owned-shoes/notes/{note_id}`. `mileage_at_note` is always set server-side from the
  shoe's current mileage at write time — never client-supplied.
- MCP: `update_shoe_notes` removed (the column it wrote no longer exists); replaced by
  `get_shoe_notes(owned_shoe_id)` and `add_shoe_note(owned_shoe_id, body)`.
- Frontend: vertical timeline in `ShoeDetail.jsx` (date · mileage · checkpoint badge when
  applicable · body), "Add note" button, per-entry delete with confirmation, empty state.

**[ADDED] 100km mileage checkpoints prompt for a journal entry.**
- `POST /owned-shoes/{id}/log-run` now returns `LogRunResponse` (`run_logged`, `updated_mileage`,
  `checkpoint_reached`, `checkpoint_km`, `shoe`) instead of the bare shoe — a breaking response-
  shape change for that one endpoint. Checkpoint crossing is `floor(new_mileage/100) >
  floor(old_mileage/100)`, e.g. 290.06km + 10km run → checkpoint_km=300.
- New shared `frontend/src/components/LogRunDialog.jsx` — logs the run, and if `checkpoint_reached`
  is true and this checkpoint hasn't been prompted before, swaps to a "Your [shoe] just hit Xkm —
  add a note?" view. "Already prompted" is tracked client-side only
  (`frontend/src/lib/checkpoints.js`, localStorage keyed by shoe id + checkpoint km).

---

## 🆕 Run pace/HR, lifetime averages, run deletion — 2026-06-24

**[ADDED] avg_pace/avg_hr wired through properly, lifetime stats, and the ability to remove a logged run.**
- `log_run_to_shoe` (MCP) gained `avg_pace`/`avg_hr` params. New computed fields on
  `OwnedShoeResponse`: `lifetime_avg_pace`, `lifetime_avg_hr`, `total_runs`. Pace strings are
  averaged correctly — converted to seconds, averaged, formatted back (`_pace_to_seconds` /
  `_seconds_to_pace` in `routers/owned_shoes.py`). Computed by `_attach_computed_fields`, called
  from every owned_shoes endpoint that returns a shoe.
- **[ADDED]** `DELETE /api/owned-shoes/runs/{run_id}` — deletes the run and subtracts its
  `distance_km` back out of the parent shoe's `current_mileage` (floored at 0), returns the
  updated shoe. New MCP tool `delete_shoe_run(run_id)` mirrors it. Frontend: Trash icon per row
  with confirmation dialog. `useDeleteShoeRun` optimistically patches the cache in `onMutate`.

---

## 🆕 My Shoes UI polish — 2026-06-24

**[ADDED] Search, active/retired split, compact mileage text, and product images on owned shoe cards.**
- Renamed "Shoes" nav tab to **"Tracked Shoes"** to disambiguate from "My Shoes".
- My Shoes page has a client-side search bar and splits cards into **Active** and **Retired** sections.
- **Images on owned shoe cards**: priority is manual `image_url` (new nullable column on
  `owned_shoes`, migration `backend/migrate_add_owned_shoe_image.py`) → best-effort
  `matched_image_url` (heuristic join against `price_records.image_url` by brand/model substring)
  → placeholder. Never a broken `<img>`.

---

## 🆕 "My Shoes" personal rotation tracker — 2026-06-24

**[ADDED] Track owned shoes (mileage, notes, run history) — separate from deal tracking.**
- New tables `owned_shoes` + `shoe_runs` (`models.py`), created automatically by `init_db()`.
  Deliberately **not** the same table as `Shoe` (deal tracking).
- Backend: `app/routers/owned_shoes.py` — full CRUD + `POST /{id}/log-run` + `GET /{id}/runs`.
  `shoe_runs.source` is `"manual"` for now; `"coros"` is reserved for future COROS sync.
- MCP: 5 tools — `get_owned_shoes`, `get_shoe_runs`, `log_run_to_shoe`, `add_shoe_note`,
  `get_shoe_notes`, `delete_shoe_run`, `retire_shoe`.
- Frontend: `pages/MyShoes.jsx`, `OwnedShoeForm.jsx`, `LogRunDialog.jsx`,
  `MileageProgressBar.jsx` (green <500km / yellow 500–800km / red >800km).

---

## 🆕 Sporting Life investigated — blocked by Cloudflare — 2026-06-22

**[BLOCKED]** Sits behind a Cloudflare managed JS challenge — 403s plain requests AND headless
Playwright. Would need a paid proxy/unblocking service (ScraperAPI, Bright Data). Not added.

---

## 🆕 New retailer — En Route Run — 2026-06-22

**[ADDED] `EnRouteRunScraper`** (`app/scrapers/enroute_run.py`).
- Shopify-backed but headless Astro storefront — `/products.json`, `/products/<handle>.js`,
  `/search/suggest.json` all 404. Bespoke scraper parses inline Astro/Qwik hydration JSON
  (`_parse_variant_blocks()` unescapes HTML-entity-encoded variant data).
- Verified: Adidas Adizero Adios Pro 4 — genuine markdowns found end-to-end.

---

## 🆕 Phase 5 — 2026-06-18 (images, colorway consolidation, +3 retailers)

**Task 2 — Product images + colorway.**
- New nullable columns `image_url` + `colorway` on `price_records` and `deals`
  (migration `backend/migrate_add_images.py`).
- Algolia scrapers: image from S3 CDN URL, colorway from `thumbnails[].color_name`.
- Shopify scrapers: `image`/`featured_image`, protocol-relative normalized to `https:`,
  colorway from the Color option.

**Task 3 — Colorway consolidation UI.**
- `Deals.jsx` groups active deals by `shoe_id` — one card per model.
- `ShoeProductCard.jsx` + `ColorwaySelector.jsx` (thumbnail gallery switching active colorway).

**Task 1 — Automatic Algolia credential rediscovery.**
- `base_scraper.discover_algolia_credentials()` drives the site's own search with headless
  Playwright, intercepts `*.algolia.net` XHR to recover app id/key/index.
- `algolia_scraper._algolia_query` detects 401/403, rediscovers once per session, caches creds.

**Task 4 — +3 Shopify retailers.** Boutique Endurance, Le Coureur, BlackToe Running added.

---

*Reference material moved to `docs/` — see `docs/architecture.md` (the Retailer Status table now lives in its §10). Stale pre-Phase-5 overview sections were removed here 2026-07-06 (R1.2); session changelog entries above are untouched and remain the authoritative history. New session entries go at the top.*
