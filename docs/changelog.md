# Anton — Session Changelog

**Last Updated:** 2026-07-07
**Status / current focus:** see `docs/project_state.md` (the perishable snapshot). This file is the append-only session log — the authoritative record of *what happened*; the `docs/` suite is the reference material.

---

## 🏁 R2.7 Session 3 — race↔activity link + COROS-name tag inference (T7–T8) — Phase 2 Session H — 2026-07-08

**[ADDED/CHANGED] The final R2.7 session — closes the milestone (all eight sub-items T1–T8 shipped). T7 back-links a completed race to the canonical run it was; T8 suggests an activity tag from the COROS activity name at sync time. Two `r2:` commits. Suite 106 → 126. One live migration (T7) — E4 reconciled.**

- **[ADDED] T7 — `planned_races.activity_id` link.** Reversible additive migration `a7b8c9d0e1f2` adds a nullable `activity_id` FK from `planned_races` to `activities`. `PlannedRace` gains the column + an `activity` relationship (no `back_populates` — activities needn't know). `races.create_completed_from_activity` (the T6 promote-to-race flow) now sets it, so a promoted race deep-links to its run; `PlannedRaceResponse` and `race_to_dict` surface `activity_id`. Frontend: the Races card's **past-race rows become tappable links** to `/activities/:id` when linked (null-guarded — planned/manually-completed races without a link render as before). **E4:** live DB backed up (`shoe_deals.db.2026-07-08-pre-r2.7-t7.bak`) and reconciled — 936 activities / 3 planned_races unchanged, additive column present. The migration was auto-applied to the live DB by the running dev server's reload (R2.2 startup runs `alembic upgrade head`). Fresh up/down round-trips clean. +2 tests.
- **[ADDED] T8 — COROS-name tag inference (suggestion only).** New pure helper `activity_tags.suggest_tag_from_name(name)` beside the vocabulary: ordered case-insensitive keyword rules (`parkrun`→Parkrun · `interval`/`repeat`→Intervals · `track`→Track · `tempo`/`threshold`→Tempo · `long run`/`long`→Long Run · `trail`→Trail · `race`/`marathon`→Race · `recovery`/`easy`/`jog`→Easy · else None), first-match precedence so specificity wins (parkrun before race; long run before easy). The `sync_coros_runs` MCP prompt now spells out the same rules so the agent surfaces the suggested tag in the confirmation table — **never auto-applied** (C9); the runner confirms or overrides. No new endpoint (the tag reaches the DB through the existing T2 `confirm_coros_run` path). +18 test cases (each keyword mapping, case-insensitivity, precedence, no-match/empty/None, and that every suggestion is valid vocabulary).
- **[VERIFIED] Suite 106 → 126** (+2 T7 in `test_races.py`, +18 T8 cases in `test_activity_tags.py`). `vite build` clean (T7's Races-card change; chunk-size warning pre-existing). **T7 UI visual pass:** the change is additive and null-guarded (a link wrapper on completed-race rows that carry a link); build-verified. Recommend an eyeball after promoting an activity to a race — the three pre-existing planned_races rows have no `activity_id`, so the link only appears for newly-promoted races. **[DOCS]** No new design_decisions entry — the tag vocabulary (B15) already covers T8's inference as a schema-grade list; T7 is a plain additive FK. Roadmap §R2.7 marked complete; project_state refreshed. **R2.7 (Training & Activity Depth) is done end-to-end.**

---

## 🏃 R2.7 Session 2 — Training display + fitness + activity edit (T4–T6) — Phase 2 Session G — 2026-07-08

**[ADDED/CHANGED] Second execution session of R2.7. Built the display improvements, the athlete-fitness surface, and the activity edit/reassign workflow: month-labelled volume axis, a shared date-range picker, a COROS fitness card, and a full `/activities/:id` detail page with shoe reassignment (through the mileage ledger) and race promotion. Four `r2:` commits (T4a, T4b, T5, T6). Suite 97 → 106. Two live migrations (T5) — E4 reconciled.**

- **[CHANGED] T4a — month axis on the weekly volume chart.** The weekly view labelled its x-axis by ISO week number (W18…); it now labels by month (May/Jun/Jul), one tick at each month's first week (month derived from the week's ISO-Thursday). Data stays weekly; display-only. `VolumeChart` gained optional `xTicks`/`xTickFormatter`. Verified on the running app.
- **[ADDED/CHANGED] T4b — date-range filtering.** Backend: `unified_activities` and `training_summary` (and `/api/activities`, `/api/training/summary`) take inclusive `date_from`/`date_to` — a superset of the existing year/month filters (the roadmap's claim that `/api/activities` already had these was wrong; corrected). UI: a shared date-range picker in the Trends header (default last 90 days, React state only, 90d/6mo/1y presets) drives the volume chart (via a ranged summary query) and the activities list; the four stat tiles keep their fixed windows on unranged data. The Activities section's **Year select was removed** — the range is now the single time control (avoids a year-vs-range conflict). +1 backend test; desktop + ~380 px verified.
- **[ADDED] T5 — athlete fitness metrics.** New append-only `athlete_metrics` table (migration `f6a7b8c9d0e1`): `vo2max`, `threshold_pace_s_per_km`, `race_predictions` (JSON), server-stamped `captured_at`. `services/fitness.py` (`record_snapshot`/`latest`), `GET /api/training/fitness` (latest, or `has_data=false` — absence isn't an error), and a `record_athlete_metrics` MCP tool. **D1 resolved:** server-side COROS is dormant (C6), so the snapshot is recorded by the Claude-Desktop sync agent — the tool docstring points it at COROS `queryFitnessAssessmentOverview` and requires runner confirmation (C9). A Training-tab Fitness card (VO₂ max, threshold pace, 5K/10K/Half/Full predictions) renders only when a snapshot exists. Verified on the running app with a temporary snapshot (since removed). +2 tests.
- **[ADDED] T6 — activity detail/edit + reassignment + race promotion.** New `rotation.reassign_attribution(activity_id, new_shoe_id)` moves a run's attribution and its distance between both shoes **through the INV-1 ledger** (never a raw ORM write); creates the attribution if the run was unattributed; no-op when already that shoe; leaves the Activity row itself intact (contrast `delete_run`); INV-3 (unique attribution) preserved. `activities.get_activity_detail`/`update_activity` (partial tag/name/description via an `_UNSET` sentinel); `races.create_completed_from_activity` (promote-to-race, prefilling date/distance/result/`status=completed`). Endpoints: `GET /activities/{id}`, `PATCH /activities/{id}` (tag validated), `POST /activities/{id}/reassign-shoe`, `POST /activities/{id}/promote-to-race`. Frontend: a routed `/activities/:id` detail page (view all fields, edit tag/name/notes, shoe-picker reassignment, "Add to races" when tagged Race); activity rows link to it and show the tag. Mutations invalidate activities/owned-shoes/training/home/races. +6 tests; detail page verified desktop + ~380 px, 0 console errors.
- **[VERIFIED] Suite 97 → 106** (+1 T4b, +2 T5, +6 T6, +existing kept green). `vite build` clean; desktop + ~380 px passes for T4a/T4b/T5/T6 with 0 console errors (verified live via the running app). **E4:** the T5 migration was applied to the live DB after a named backup (`…-pre-r2.7-t5.bak`) with count reconciliation (936 activities unchanged; new table only). **[DOCS]** CLAUDE.md §14 INV-1 now lists `rotation.reassign_attribution` as a ledger-mutating path; roadmap §R2.7 Session-2 tasks marked; project_state refreshed. **Remaining R2.7: Session 3 — T7 (race↔activity FK link) + T8 (COROS-name tag inference).**

---

## 🏃 R2.7 Session 1 — Training depth foundation (T1–T3) — Phase 2 Session F — 2026-07-07

**[ADDED/CHANGED] First execution session of R2.7 (Training & Activity Depth), after committing `TRAINING_DEPTH_PLAN.md` (the §-numbered T1–T8 milestone contract). Landed the schema foundation and the PB correctness fix: activity tagging + richer COROS capture + an eligibility filter that stops interval sessions faking distance records. Four `r2:` commits (plan + T1 + T2 + T3). Suite 88 → 97.**

- **[ADDED] Plan — `TRAINING_DEPTH_PLAN.md`.** Grounds the eight roadmap sub-items in the actual code (corrected two roadmap claims: `Activity` already carries name/elapsed/elevation/cadence/calories so T1 adds only 4 columns; `/api/activities` takes `year/month`, **not** `date_from/date_to` as the roadmap stated — T4b now includes adding them). Sequences T1→T2→T3, then T4/T5/T6, then T7/T8 across ~3 sessions; records discovery steps (COROS field coverage) and open questions with recommended defaults.
- **[ADDED] T1 — activity tags + fitness columns.** Reversible migration `e5f6a7b8c9d0` adds four nullable columns to `activities`: `training_load`, `training_focus`, `activity_tag` (indexed — the PB query filters on it), `best_km_pace_s`. The backend-owned tag vocabulary lives in a pure module (`app/utils/activity_tags.py`, `ACTIVITY_TAGS` — Easy · Long Run · Recovery · Tempo · Intervals · Track · Workout · Trail · Parkrun · Race) served at `GET /api/activities/tags` so the frontend keeps no independent copy — the pattern R2.4 will mirror for `shoe_type`. The `UnifiedActivity` seam gains `activity_tag`, `elapsed_time_s`, `activity_id` (needed by T3/T6). **E4:** live DB backed up (`shoe_deals.db.2026-07-07-pre-r2.7-t1.bak`), reconciled — 936 activities / 701 runs / 9091.79 km / 670 attributed unchanged; fresh up/down round-trips clean. +3 tests.
- **[CHANGED] T2 — COROS field population.** The sanctioned write path now stores the per-run fields the sync used to discard: `name`, `elevation_gain_m`, `moving_time_s`, `elapsed_time_s`, `avg_cadence`, `calories`, `training_load`, `training_focus`, plus a confirmed `activity_tag`. Widened `rotation.log_run` (the single run writer — INV-2, no parallel path), `coros.confirm_run`, and the `confirm_coros_run` MCP tool with matching keyword-only optional params; all nullable so manual/Strava callers omit them. **C9:** the tool validates `activity_tag` against the vocabulary (rejects unknown), and the `sync_coros_runs` prompt now tells the agent to surface an unmapped-tag guess for the runner to confirm/override, never apply silently. Idempotent re-confirm unchanged (INV-5). +2 tests.
- **[CHANGED] T3 — PB eligibility fix.** The bug: a stop-heavy interval session could match a race distance at rep pace and register a false "5k record". `strava_stats.personal_bests()` now filters — Intervals/Track always excluded, Race/Parkrun always included, other run tags included, untagged excluded only when stop-heavy (`elapsed_time_s > 1.5 × moving_time_s`, the fallback for the untagged archive). The classifier (`activity_tags.pb_exclusion_reason`) sits beside the vocabulary. The response gained transparency fields: `personal_bests` returns a `PersonalBestsResult` (records + `excluded_count` + `excluded_reason`); `/api/training/records` wraps it (`PersonalBestsResponse` — an object now, not a bare array), the `get_personal_bests` MCP tool surfaces the counts, and the Training Records card shows "N excluded (…) — tag to reconsider". +4 tests (interval exclusion, race-always-in, elapsed guard, its exact 1.5× boundary).
- **[VERIFIED] Suite 88 → 97** (+3 T1, +2 T2, +4 T3, and the existing `test_records_attribute_shoe` updated for the new PB shape). `vite build` clean (T3's Records-card change; chunk-size warning is pre-existing). **Visual pass deferred** — the user's running dev server predates these changes and the R2.2-moved DB; the UI change is additive and null-guarded (recommend an eyeball on the Records card after the pending restart). **T3 changed the `/api/training/records` contract** from an array to `{records, excluded_count, excluded_reason}`; the frontend was updated in the same commit, but any other consumer must adapt. **[DOCS]** design_decisions gains B15 (activity-tag vocabulary) and B16 (PB eligibility rule); roadmap §R2.7 T1–T3 marked done; TRAINING_DEPTH_PLAN Session-1 tasks complete.

---

## 🗄️ R2.2 — Alembic is the sole schema authority — Phase 2 Session E — 2026-07-07

**[CHANGED/REMOVED] The schema now has exactly one authority. Startup stopped calling `Base.metadata.create_all` and instead runs `alembic upgrade head`; `create_all` survives only in the test fixtures. This closes the dual-authority trap (design_decisions A6, CLAUDE.md §9): a model edit without a migration can no longer be silently papered over on a live DB. The nine pre-Alembic `legacy_migrations/` scripts are deleted, and the live DB + all backups moved out of the repo tree to `~/anton-data/`. Three `r2:` commits, one per task. Suite 88 → 88 (unchanged — no behavior change, all-green throughout).** *(design_decisions A6 → 🔁 Superseded.)*

- **[CHANGED] Task 1 — Alembic sole authority.** New `database.run_migrations()` (programmatic `alembic upgrade head`) replaces the `init_db()`/`create_all` boot path in `main.py`'s lifespan; `seed_data.py` and the export-generated seed script call it too. The formerly-**empty** baseline revision (`cf1eccba0a79`) was the reason fresh setups still needed `create_all` — it stamped an already-populated DB and created nothing. It now recreates the exact pre-Alembic schema, captured provably: take the current models, `create_all` them, `alembic downgrade` every later migration back to baseline, dump the resulting schema. **Verified:** a fresh `upgrade head` builds a DB matching the models *table-for-table* (owned_shoes.mileage_limit, activities, planned_races all present via the later migrations); the baseline round-trips (`upgrade head` → `downgrade base` → 0 tables); the live DB (already stamped at head) treats `run_migrations()` as a no-op. `create_all` now lives only in `tests/conftest.py` + `tests/test_auth.py`.
- **[REMOVED] Task 2 — `legacy_migrations/` deleted.** The nine ad-hoc `migrate_add_*.py` scripts (marked "do not run") predated Alembic and had no remaining role once the baseline recreates their schema. Removed from the tree; git history is the archive. No code referenced them (grep-verified — only docs, updated here).
- **[CHANGED] Task 3 — live DB + backups relocated to `~/anton-data/`.** The 15 MB live SQLite file moved via atomic same-filesystem rename (the running dev server's open fd follows the inode — no data-loss window) to `~/anton-data/shoe_deals.db`; the seven historical `.bak` files + a fresh dated pre-relocate backup moved to `~/anton-data/backups/`. `DATABASE_URL` now an absolute path (`.env`); `.env.example` documents the convention and a dated-backup naming scheme (`shoe_deals.db.<YYYY-MM-DD>-<label>.bak`). Untracked the three `.bak` files that had been committed before the ignore rule existed (`git rm --cached`) and added `*.db.bak*` to `backend/.gitignore`. **Verified:** the app boots and reads the relocated live DB (936 activities). **Go-live is a human step:** the running dev server still uses the old path via its open fd — restart it to pick up the new `DATABASE_URL` (this pairs naturally with the R2.1 `ANTON_SECRET` restart still pending from Session D).
- **[VERIFIED] Full suite green at 88** (unchanged — this session changed schema *management*, not schema or behavior). No `vite build` needed (no frontend change). No new migration (the baseline was *populated*, not added — it only ever runs on fresh DBs, never on the live one). **[DOCS]** design_decisions A6 → 🔁 Superseded (entry + table row); architecture.md §5/§16.2 references updated; roadmap R2.2 row moved to project_state §3.

---

## 🔐 R2.1 — the security pass: bearer-token auth on every surface — Phase 2 Session D — 2026-07-07

**[ADDED/CHANGED] Anton's trust model moves from a *network* property ("only things that can reach port 8000 can mutate") to an *application* property ("only requests carrying the shared secret can mutate"). One shared bearer token (`ANTON_SECRET`) now gates `/api/*` and `/mcp`; the default bind is loopback; all three consumers (SPA, Claude Desktop, the Son-of-Anton loopback) send the token. This is the standing gate in front of every exposure-increasing R3–R5 feature. Executed `SECURITY_PASS_PLAN.md` §4 in order, one `r2:` commit per task. Suite 75 → 88.** *(design_decisions E1 → Superseded by new E7.)*

- **[ADDED] §7 pre-work — resolved the plan's three open questions** (`SECURITY_PASS_PLAN.md` §8 addendum, verified first-hand): **Q1** browser token = build-time `VITE_ANTON_SECRET` (rejected the `/api/config` pre-auth endpoint — complexity with no gain under the LAN threat model); **Q2** `mcp-remote --header` **confirmed supported** in the installed/latest `0.1.38` (read `parseCommandLineArgs` in the resolved package — no upgrade needed; noted the orthogonal local Node v19.4.0 `mcp-remote` crash as a non-blocker); **Q3** no hot-rotation — documented the 3-step `.env`-edit + restart procedure. Resolved **Q4** (middleware-vs-mount ordering) during implementation and asserted it in tests.
- **[ADDED] §4.1 — `ANTON_SECRET`/`VITE_ANTON_SECRET` in `.env.example` + startup fail-fast.** `main.require_anton_secret()` runs at lifespan startup and aborts the boot with a clear message if the secret is unset/empty — auth is *not* an optional feature (contrast CLAUDE.md §4.6 graceful degradation), so absence is fatal. Placed in the lifespan (not module import) so scripts/tests that don't serve requests are unaffected.
- **[ADDED] §4.2 — the auth middleware** (`app/middleware/auth.py`). A **pure ASGI** middleware (not `BaseHTTPMiddleware`) so SSE + the `/mcp` Streamable-HTTP transport stream through untouched; constant-time compare (`secrets.compare_digest`); an empty configured secret denies everything; **401 with an empty body** (no reason string, no `WWW-Authenticate`). Exempts `/`, `/health`, `/api/health` (new liveness alias) and all `OPTIONS` (CORS preflight). Registered **before** `CORSMiddleware` so CORS stays the outer wrapper and 401s still carry CORS headers. **One middleware covers the mounted `/mcp` sub-app** — asserted, not assumed (test below).
- **[CHANGED] §4.3 — default bind `0.0.0.0` → `127.0.0.1`** (`run.py`). Loopback-only is now an app property; `API_HOST=0.0.0.0` remains the explicit, now-safe LAN opt-in (documented in `.env.example`).
- **[CHANGED] §4.4 — the SPA sends the token on every request path.** `api.js` reads `VITE_ANTON_SECRET`, an axios request interceptor injects `Authorization` on all axios calls, and an exported `authHeaders()` single-sources the header for the paths that bypass axios: the chat `fetch()` calls (`/chat/message`, `/chat/resources`, `/chat/resource/read`, `/chat/providers`). **The scrape SSE was converted from a native `EventSource` (which can't send an `Authorization` header) to a `fetch()` ReadableStream reader** (frame parsing mirrors `useChatStream`; behavior preserved — retailer-done cache patch, completed→invalidate, drop→connectionLost, reattach-via-replay; `AbortController` replaces `es.close()`). Missing token → one console warning, not a hard failure (dev without `.env`). `vite build` clean.
- **[CHANGED] §4.5 — loopback client sends the token** (`chat_service.py`). Son of Anton is an MCP client of this same process's `/mcp` (the loopback, dependency_graph §8.1); once `/mcp` requires the token this client must send it or the assistant *silently* loses all tools. Added an `auth_loopback` flag on the `MCP_SERVERS` entry and a `_server_headers()` helper that attaches the token **at connect time** (chat_service is imported before `main`'s `load_dotenv`, so import-time `getenv` could capture an empty value) and **only** for the loopback entry (never leak the secret to a future external MCP server). Both `ClientSessionGroup` connect sites use it.
- **[ADDED] §4.6 — `CLAUDE_DESKTOP_SETUP.md`** (QUICKSTART.md is stale from the review): the before/after `mcp-remote` config adding `--header "Authorization: Bearer <ANTON_SECRET>"`, the literal-token-vs-`${ENV}` rationale, the Node-crash caveat, the breaking-change rollout order (**Desktop config before server restart**), and the rotation procedure.
- **[CHANGED] §4.7 — admin force-release endpoint gated.** `POST /api/admin/scrape-lock/release` (M3, Session C) is now behind the token via the middleware; removed its "intentionally unauthenticated for now (E1)" docstring note.
- **[ADDED] §4.8 — `tests/test_auth.py`, the suite's first HTTP-layer tests** (13). Driven via `httpx.ASGITransport` + `asyncio.run` in sync tests — the installed **httpx 0.28 dropped Starlette `TestClient`'s `app=` shortcut**, and the FastAPI/Starlette/sse-starlette pin triple (A7) is untouchable, so this is the robust path (no new dep; `StaticPool` in-memory DB so the threadpool-run route sees the tables). Covers: unauth `/api/owned-shoes`, `/api/chat/message`, `DELETE`, `/api/admin/scrape-lock/release`, and **`/mcp`** all 401; wrong token 401; 401 body empty; `/health`, `/api/health`, `/` open without token; authed `/api/owned-shoes` reaches the route (200, not 401); OPTIONS preflight not blocked.
- **[VERIFIED] Suite 88 passing** (75 → 88; +13 `test_auth.py`). `vite build` clean. Middleware behavior verified end-to-end via `ASGITransport` against the real app (health open, `/api` + `/mcp` 401 unauth, authed passes, OPTIONS open); loopback header injection verified at the `_server_headers()` seam. **Live go-live is a human step** — set `ANTON_SECRET`/`VITE_ANTON_SECRET`, update the Desktop `--header`, then restart the server (fail-fast). The end-to-end live smoke (real Claude Desktop sync, a real chat message spending LLM credits) is **not** run here: the user's dev servers run older code, the secret isn't set yet, and restarting mid-session would break Desktop before its config is updated — the runbook in `CLAUDE_DESKTOP_SETUP.md` §"Rollout order" is the ordered checklist. **Rate limiting on `/api/chat/message` remains a separate R2 item** (plan §6).
- **[DOCS]** design_decisions **E1 → 🔁 Superseded by E7** (new entry: the bearer-token decision, its threat model, and rejected alternatives), Superseded table row added.

---

## 🔒 Safety fixes (C1 + M3) + SECURITY_PASS_PLAN — Phase 2 Session C — 2026-07-07

**[CHANGED/ADDED] The bridge session between R1 (closed) and R2. Two same-day safety fixes from the code review — the writable mileage ledger (C1) and the scrape-lock wedge (M3) — plus the plan doc that gates R2.1, the security pass. No auth code this session (the plan comes first, by design). Three `r2:` commits, one per task. Suite 67 → 75.**

- **[CHANGED] Task 1 — C1: mileage ledger no longer writable via `PUT /owned-shoes/{id}`.** `OwnedShoeUpdate` exposed `current_mileage` (and `starting_mileage`) as writable fields applied through a blind `setattr` loop, so any client could set the counter to an arbitrary value — bypassing `rotation.log_run` and breaking INV-1 (`current_mileage = starting_mileage + Σ attributed distances`). The frontend used this deliberately (the ShoeDetail "Adjust mileage" dialog + an editable field on the edit form), making it an *undocumented invariant exception*. Fix: removed both fields from `OwnedShoeUpdate` (`starting_mileage` is now immutable post-create — the edit form already disabled it); added the sanctioned `rotation.adjust_mileage()` behind **`POST /owned-shoes/{id}/adjust-mileage`**, which records the override as a journal note (`triggered_by="mileage_adjustment"`) so a later COROS/Strava reconciliation can explain the drift — the third blessed exception to the single-write-path rule. Repointed the ShoeDetail adjust dialog to the new endpoint (`useAdjustMileage`); removed the redundant current-mileage field from `OwnedShoeForm` (mileage edits now go through the one dialog). **Verified:** 4 new tests in `tests/test_owned_shoes.py` (PUT drops `current_mileage`/`starting_mileage`; `adjust_mileage` sets the value + writes the note; missing-shoe raises). Updated `CLAUDE.md` §14 INV-1; struck C1 in `refactor.md` and P0-1 in `tech_debt.md`. *(refactor.md C1; domain_model §4.5/§4.6.)*
- **[CHANGED/ADDED] Task 2 — M3: scrape-lock wedge protection.** `scrape_runner.run_scrape_job` ran its setup block (shoe/retailer queries, promo detection) **before** the `try/finally` that releases the process-wide scrape lock, so a transient setup failure exited with the lock held — wedging every subsequent scrape (REST, MCP, background) at 409 until a process restart, with no UI explanation. Fix: the whole body now runs under the lock-releasing `finally`; `release_scrape_lock()` is tolerant of an unheld lock (no more `RuntimeError` on double-release). Added the operational escape hatch **`force_release_scrape_lock()`** behind **`POST /api/admin/scrape-lock/release`** (`{"was_held": bool}`) and a synchronous **`GET /api/scrape/status`** (`{"scrape_running": bool}`) for MCP/admin checks. Docstring on `lock.py` states the in-memory single-process constraint and the R4.1/D4 replacement requirement. *(The other lock sites — the REST `scrape_guard()` paths and MCP `trigger_scrape` — were verified already correct.)* The admin endpoint is **intentionally unauthenticated for now** (E1), and R2.1 gates it. **Verified:** 4 new tests in `tests/test_scrape_lock.py` (force-release false when unheld, true + released when held, tolerant double-release, status reflects the lock). Struck M3 in `refactor.md` / `tech_debt.md`. *(refactor.md M3; design_decisions D4.)*
- **[ADDED] Task 3 — `SECURITY_PASS_PLAN.md` (repo root) gates R2.1.** The session's main output. Covers: scope + the explicit **LAN threat model** (untrusted processes on the same network, not the internet) and non-goals — no multi-tenancy/OAuth/HTTPS/rate-limiting (§1); the full unauthenticated-surface inventory, including the **loopback self-connection** (`chat_service → MCP_SERVER_URL → this same `/mcp`) whose client must also send the token or Son of Anton silently loses its tools — dependency_graph §8.1 (§2); the chosen **single shared bearer token** (`ANTON_SECRET`) with alternatives rejected (§3); an ordered, one-commit-per-task implementation list — auth middleware, `127.0.0.1` default via the existing `API_HOST` env, SPA axios interceptor, loopback header injection at the existing `headers=` seam, `mcp-remote --header`, admin-endpoint gating, and the first `TestClient` HTTP-layer tests (§4); the breaking-change **rollout sequence** for Claude Desktop (§5); explicit scope boundaries (§6); and open questions to resolve first — browser token delivery, `mcp-remote --header` support, middleware-vs-mount ordering for `/mcp` (§7). No R2.1 code written — that is the next session.

- **[VERIFIED] Full suite green at 75** (67 → 75; +4 `test_owned_shoes.py`, +4 `test_scrape_lock.py`). `vite build` clean; the only UI changes are the mileage-edit consolidation in Task 1 (redundant form field removed, adjust dialog repointed to the new endpoint — behavior preserved). Freshness note: `models.py` is now 19,246 bytes (was 18,858 at the `ai_context.md` snapshot) from R1.4's `ShoeRun` WARNING comment — a comment, not a schema change.

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
