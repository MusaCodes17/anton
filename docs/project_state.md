# Anton — Project State

**Snapshot date:** 2026-07-08 (after Phase 2 Session J — **chat rate limiting**, the R2.1-adjacent throttle. An in-process token-bucket limiter (`services/rate_limit.py`) caps `POST /api/chat/message` per client IP — 429 + `Retry-After`, default 20/min — so an *authenticated* client can't loop and burn paid LLM credits (R2.1 only stopped *anonymous* spend). design_decisions E8. Suite 128 → **133**. Prior: Session I **R2.3 indexed reads + watchlist service** (suite → 128); Session H **R2.7 T7–T8 + Training polish**; Sessions F/G **R2.7 T1–T6**; Session E **R2.2**; Session D **R2.1**. **R2.7 + R2.3 + rate limiting done; next active R2 item is R2.4 shoe-type controlled vocabulary.**)
**Read this first, then:** `docs/ai_context.md` → `docs/architecture.md` → `docs/domain_model.md`. This file is the *perishable* one — it describes a moment, and staleness here is expected and fixable; update it at the end of every working session.

---

## 1. Sixty-Second Summary

Anton (repo name: `running-shoe-deals`) is a **single-user personal running platform**: shoe-deal watching across 8 Canadian retailers + a canonical run/training history + shoe rotation wear tracking, with an embedded AI assistant (Son of Anton) and a full MCP server used by Claude Desktop. FastAPI + SQLite + React SPA, all local, no auth (deliberate, deferred).

**Where things stand right now:** the multi-phase **Anton redesign is functionally complete** — all five tabs (Home / Training / Shoes / Deals / Son of Anton) are built. The two most recent structural events: the canonical `activities` table (2026-07-04, reversible reconciled migration) and **MSRP-drives-deals** (2026-07-06 — deal qualification and savings now measured against MSRP; `target_price` demoted to an optional threshold; migration `d4e5f6a7b8c9`). The suite is green at **67 tests**. What remains of Phase 5 is the agent work (Deal Alert / Weekly Rotation Summary) and durability items. The **documentation program** (`documentation_creation.md`) is **complete and committed** (R1.1, 2026-07-06). **Phase 2 implementation has begun: all of roadmap R1 is now closed** (Session B, 2026-07-07 — R1.3 replacement-deals sizes, R1.4 proxy guards, R1.5 four-part debt sweep, R1.6 APScheduler removed). **The R1→R2 bridge (Session C, 2026-07-07) then landed the two same-day safety fixes — C1 (writable mileage ledger) and M3 (scrape-lock wedge) — and wrote `SECURITY_PASS_PLAN.md`, the doc that gates R2.1.** **R2.1 — the security pass — then shipped (Session D, 2026-07-07):** a shared bearer token (`ANTON_SECRET`) now gates `/api/*` and `/mcp`, the default bind is loopback (`127.0.0.1`), and all three consumers (SPA, Claude Desktop, the Son-of-Anton loopback) send the token; suite 75 → **88**. The exposure gate in front of R3–R5 is now closed. **R2.2 — schema authority — then shipped (Session E, 2026-07-07):** Alembic is the sole schema source (startup runs `alembic upgrade head`; `create_all` is test-only; the baseline recreates the pre-Alembic schema so fresh DBs build from Alembic alone), `legacy_migrations/` deleted, and the live DB + backups relocated to `~/anton-data/`. Next in R2: 2.3 indexed reads (and the still-open rate-limiting item).

**The stated Current Focus** (per `docs/changelog.md`): *"Product images, colorway consolidation, scraper durability + coverage."* Note: images/colorways largely shipped in June — read this focus line as the *durability/polish pass* over those features plus scraper coverage, not greenfield work. (If that reading is wrong, correct this line.)

---

## 2. Current Development Status

| Track | Status |
|---|---|
| Anton redesign Phases 1–4 (IA, Deals watchlist, Training tab, Home) | ✅ Complete (Phase 4 landed 2026-07-03) |
| Phase 5 backlog | 🟡 3 of 4 items done (canonical activities ✅ 2026-07-04 · `/shoes` lifecycle reframe ✅ · app mark ✅ · **agents remaining**) |
| Strava historical import (694-run, 8-year archive) | ✅ Complete and now *structurally* permanent (absorbed into `activities`) |
| Test suite | ✅ **133 passing**, 20 modules (Session J: `test_rate_limit.py` +5; Session I: `test_activities_union.py` +1 composed filter+pagination; Session H: `test_races.py` +2, `test_activity_tags.py` +18, `test_activities_union.py` +1 (PB activity_id); Session G: `test_fitness.py` +2, `test_activity_edit.py` +6, `test_activities_union.py` +1; Session F: `test_activity_tags.py` +3, `test_activities_model.py`/`test_activities_union.py` +2/+4; `test_auth.py` +13 Session D) |
| Documentation program | ✅ **Complete and committed** (R1.1, 2026-07-06) — full `docs/` suite + `CLAUDE.md` (incl. §14 INVARIANTS) + `refactoring/` + final review + reconciliation + `.claude/skills/` (13 workflow skills) |
| Roadmap R1 (loose ends) | ✅ **Complete** (2026-07-07) — R1.1/R1.2 docs, R1.3 replacement-deals card, R1.4 proxy guards, R1.5 debt sweep (Task D · shim delete · pure `pace` · chat catalog), R1.6 APScheduler removed |
| Review safety fixes (C1 / M3) | ✅ **Resolved** (Session C, 2026-07-07) — mileage ledger no longer writable via PUT (sanctioned `adjust_mileage` path); scrape-lock wedge closed + admin force-release/status endpoints |
| Security pass (R2.1) | ✅ **Shipped** (Session D, 2026-07-07) — shared bearer token on `/api`+`/mcp` (pure-ASGI middleware), `127.0.0.1` default bind, fail-fast on missing secret, SPA + Desktop + loopback all send the token, 13 HTTP-layer tests. E1 → Superseded by E7. **Live activation (set `.env` secret, update Desktop `--header`, restart) is a human step** — `CLAUDE_DESKTOP_SETUP.md`. Rate limiting is a separate R2 item. |
| Schema authority (R2.2) | ✅ **Shipped** (Session E, 2026-07-07) — Alembic sole source: startup runs `alembic upgrade head` (`database.run_migrations()`), `create_all` demoted to test fixtures, baseline revision recreates the pre-Alembic schema (fresh DB builds from Alembic alone), `legacy_migrations/` deleted, live DB + backups moved to `~/anton-data/`. A6 → Superseded. **Server restart needed** to pick up the new `DATABASE_URL` (pairs with the R2.1 restart). |
| Training depth (R2.7) | ✅ **Complete** (Sessions 1–3: F/G/H, 2026-07-07→08) — T1 tag vocabulary + 4 `activities` columns · T2 COROS field population · T3 PB eligibility fix · T4a month volume axis · T4b date-range picker · T5 `athlete_metrics` + fitness card · T6 `/activities/:id` edit + reassignment + race promotion · T7 `planned_races.activity_id` link · T8 COROS-name tag inference. Migrations `e5f6a7b8c9d0`, `f6a7b8c9d0e1`, `a7b8c9d0e1f2`. B15/B16 added. |

The app is in **daily real use** (live DB is the only DB: 933 activities, 698 runs, 8,028 km, 667 attributed).

---

## 3. Features Completed

Grouped; dates are `docs/changelog.md` entries.

**Deal watching**
- Watchlist CRUD (size-less tracking, target vs MSRP), 8 working retailer scrapers (2 Algolia, 5 Shopify, 1 bespoke headless-Astro), platform auto-detection for new retailers, scrapability dry-run test (2026-06).
- Deal qualification + honest retirement (requalification & orphaning with non-empty guard); append-only price history; product images + colorway consolidation UI; promo-code detection with manual-beats-scraped (2026-06-18 →).
- **MSRP drives deals (B9-v2)** — a deal is any retailer price below the shoe's MSRP; savings measured against MSRP; `target_price` demoted to an optional personal threshold. Migration `d4e5f6a7b8c9` + live-DB recompute (113→112 active deals); 3 new tests (2026-07-06).
- Algolia credential self-rediscovery (self-healing 401/403) (2026-06-18).
- Background concurrent scrape-all with SSE progress + replay; process-wide scrape lock; per-shoe/retailer sync scrapes (refactor era).
- Deals page: on-sale grid + collapsed "Watching" section with best-ever/last-seen prices (Phase 2).

**Rotation & training**
- Owned-shoe rotation: mileage ledger, purchase price → cost/km, status lifecycle, images (manual → heuristic match → placeholder) (2026-06-24).
- Run logging with pace/HR, lifetime averages, run deletion with ledger reversal; 100 km checkpoints prompting journal entries; mileage-anchored notes journal; shoe detail page (2026-06-24).
- `/shoes` lifecycle reframe: type-grouped rotation + retirement-pipeline band (≥75%, worst-first) with replacement-deal counts, shared server-side computation (2026-07-04).
- Training tab: weekly/monthly volume trends, distance-band PBs (honestly labeled), paginated unified activities list with filters, planned-races card with countdowns/target pace (Phase 3).
- **Canonical `activities` table** — one row per physical run (strava/coros/manual), `shoe_runs` reduced to attribution, reversible migration, counters untouched, archive-preservation delete rule (2026-07-04).
- COROS sync: server-side path (dormant — see Blockers) and the working Claude-Desktop agent path (`sync_coros_runs` prompt) with confirmation gating.

**Home & shell**
- Home as attention surface: training pulse, shoe alerts, top deals, activity strip — one `GET /api/home` (~110 ms) (2026-07-03).
- Five-tab IA, Anton rebrand in UI, real brand mark + favicon (2026-07-04).

**AI layer**
- MCP server: ~20 tools, 7 resources (markdown+JSON), `sync_coros_runs` prompt, sampling-powered `draft_shoe_review`; mounted at `/mcp` with lifespan-merged session manager.
- Son of Anton: multi-provider (Anthropic/OpenAI/Gemini) streaming agentic chat, auto tool discovery via loopback MCP, resource pre-priming, @-mention resource picker, localStorage conversations.

**Engineering**
- 2026 refactor: services extraction, scraper decomposition (orchestrator/registry/deal-store/lock), Alembic adoption; Strava import pipeline with self-checking assumptions.
- **Documentation program shipped and committed (R1.1, 2026-07-06):** full `docs/` suite, `refactoring/` reviews, `CLAUDE.md` (with the §14 INVARIANTS checkable list, INV-1…INV-8), the `claude.md → docs/changelog.md` rename, and the `.claude/skills/` library (13 workflow skills per `docs/skills_library.md`; the `shoe_type` vocabulary table landed in domain_model §4.3 the same session).
- **Schema authority resolved (R2.2, Phase 2 Session E, 2026-07-07):** Alembic is the sole schema source — startup runs `alembic upgrade head` (`database.run_migrations()`) instead of `create_all` (now test-fixture-only); the baseline revision `cf1eccba0a79` recreates the exact pre-Alembic schema so a fresh DB builds from Alembic alone; `legacy_migrations/` deleted; the live DB + backups moved out of the repo tree to `~/anton-data/`. A6 → Superseded.
- **R1 debt sweep (Phase 2 Session B, 2026-07-07):** `ShoeRun.activity` eager-loaded at all five run-list seams (R1.4); `rotation.attach_computed_fields` extracted, killing the last router→router import (R1.5a); `scraper_manager` shim deleted, consumers on `ScrapeOrchestrator`/`lock`/`registry` (R1.5b); pure `app/utils/pace.py` replacing three copies (R1.5c); `chat_service.MODELS` single-sourcing the model catalog + id-based provider routing (R1.5d); APScheduler removed from `requirements.txt` (R1.6). D7 and E5 → Superseded.

**Engineering (cont.)**
- **Chat rate limiting (R2, Session J, 2026-07-08):** an in-process token-bucket limiter (`services/rate_limit.py`, per client IP) throttles `POST /api/chat/message` — 429 + `Retry-After`, default 20/min, env-tunable — so an authenticated-but-looping client can't burn paid LLM credits (completes the R2.1 spend story; E7 stopped *anonymous* spend). Single-process by design; design_decisions E8.
- **Indexed reads + watchlist service (R2.3, Session I, 2026-07-08):** `unified_activities` swapped from a whole-table Python pass to a single indexed SQL query (LEFT JOIN through `shoe_runs`→`owned_shoes`, all filters + newest-first order + LIMIT/OFFSET in the DB) behind the byte-identical seam — every caller untouched. New composite index `ix_activities_type_run_date` (migration `b8c9d0e1f2a3`, additive/reversible, E4-reconciled). `services/watchlist.py` extracted from the fat `routers/watchlist.py` (value-object dataclasses; router now a thin adapter), unblocking MCP watchlist parity (R3.4).

**Rotation & training (cont.)**
- **Replacement Deals card on `/shoes/:id`** — live section (shipped in PR #9): same-type active deals, worst-discount-first, with brand/model/retailer/price/savings-badge/link and **size availability** (added 2026-07-07, R1.3), plus loading/error/empty/no-type states.

---

## 4. Features Partially Complete

| Item | State | The missing piece |
|---|---|---|
| **Server-side COROS sync** | Code complete (`coros_client`, `coros.py`, REST endpoints), cleanly disabled | COROS won't issue Open-API credentials to individuals. Dormant by decision (design_decisions.md C6); revives only if COROS opens access. |
| **Anton rebrand** | UI, mark, favicon done | Repo name, API title ("Running Shoe Deal Finder"), DB filename still pre-brand — kept deliberately (E6). |
| **P2.3 price-history sparkline** (watchlist rows) | Was declared a cut-first stretch goal in Phase 2 | Unverified whether it shipped; treat as *probably not built*. Check `Deals.jsx` before planning. |

---

## 5. Features Planned

From the Phase-5 backlog and standing wishlist (roadmap.md — prompt 3 — will structure these properly):

- **Deal Alert Agent** and **Weekly Rotation Summary Agent** — the last Phase-5 backlog items; their natural surfaces (Home modules, Training tab) now exist by design.
- **Security pass** — API auth, rate limiting, MCP endpoint auth; the acknowledged precondition for everything below.
- **Native mobile client** — mobile-first constraints and API-first discipline already embedded for this.
- **Scheduled scraping** (roadmap R4.1) — needs a real design (persisted job state + DB-level coordination replacing the in-memory scrape lock) before a scheduler is (re)introduced; APScheduler was removed 2026-07-07 pending that design.
- **Scraper coverage**: Sport Experts (custom FGL platform, "future"); Sporting Life only via paid unblocking (declined on principle — likely permanent no).
- Explored & deferred: remote MCP transport for ChatGPT; Email MCP; Coupon Hunting Agent.
- Server-side chat/conversation persistence (currently localStorage — design_decisions.md C8, scheduled to change).

---

## 6. Known Bugs & Quirks

No open *defect* list exists — bugs get fixed in-session and logged in `docs/changelog.md`. Standing known quirks (working-as-designed-but-sharp):

1. **MCP `trigger_scrape` full-catalog reliably times out client-side** (20–30 min job vs client timeouts). Workaround: per-shoe scrapes or the web UI. Documented, not fixed.
2. **`ShoeRun` proxy hazards (since the 2026-07-04 migration):** proxied fields (`distance_km`, `avg_pace`, …) do a lazy `Activity` load per row (N+1 in un-eager-loaded loops) and **silently don't work in SQLAlchemy `filter()`** — query against `Activity` columns instead. All five run-list seams now `contains_eager(ShoeRun.activity)` (R1.4, 2026-07-07) and the model carries a WARNING comment; *new* run-list code is still where this will bite — add the eager-load.
3. **Le Coureur titles sometimes remain French** despite the `/en` locale — cosmetic, known.
4. **Two retailers permanently dark** (Sporting Life: Cloudflare; Sport Experts: unbuilt custom platform) — the deal feed silently excludes them.
5. **Checkpoint "already prompted" state is per-browser** (localStorage) — a second device will re-prompt at the same checkpoint.
6. The three legacy `GET /api/scrape/test/*` endpoints predate the universal `POST /shoes/test` and are candidates for removal, not repair.

---

## 7. Technical Debt

Full ranked treatment: `refactoring/tech_debt.md` — **the ranked authority** (P0–P3 with states); actionable detail in `refactoring/refactor.md`; deletions in `refactoring/dead_code.md`. The short list a new session must know:

- **No auth on three mutation surfaces** + default `0.0.0.0` bind (deliberate; gates all exposure). **The top open item; its plan now exists** (`SECURITY_PASS_PLAN.md`, ready to execute as R2.1).
- ~~**Dual schema authority** (`create_all` + Alembic) and DB + dated `.bak` files in the working tree.~~ resolved (R2.2, Session E, 2026-07-07 — Alembic sole authority, `create_all` test-only, DB + backups moved to `~/anton-data/`; A6 → Superseded).
- **Fat legacy routers** (`watchlist`, `deals`, `dashboard`) with inline ORM logic — also what blocks MCP watchlist parity.
- ~~**Whole-table in-Python reads** (`unified_activities`, watchlist reduction)~~ — `unified_activities` is now a single indexed SQL query (R2.3, Session I; index `ix_activities_type_run_date`). The watchlist reduction still reduces in Python but now lives in `services/watchlist.py` (labelled O(N), fine at scale); `deals`/`dashboard` fat routers remain.
- **Provider agentic loop implemented 3×** (per provider) — the model-catalog duplication half was fixed (R1.5d, 2026-07-07); the loop triplication remains (tech_debt 5.2, consolidate before the R3 agents extend it).
- ~~**Writable mileage ledger** via `PUT /owned-shoes/{id}` (P0-1)~~ resolved (C1, Session C, 2026-07-07 — sanctioned `rotation.adjust_mileage()` path). ~~**Scrape-lock wedge**~~ resolved (M3, same session — lock-releasing `finally` covers setup; admin force-release endpoint).
- ~~`scraper_manager` compat shim~~ deleted (R1.5b, 2026-07-07). ~~"Task D" router→router import~~ resolved (R1.5a). ~~Pace formatting ×3~~ resolved (R1.5c). ~~Chat catalog duplication~~ resolved (R1.5d). ~~APScheduler installed, unwired~~ removed (R1.6).

---

## 8. Current Blockers

Nothing blocks day-to-day development. External blockers, all worked around or accepted:

| Blocker | Impact | Status |
|---|---|---|
| COROS refuses individual Open-API keys | Server-side sync dormant | **Worked around** — Claude Desktop + COROS MCP + `sync_coros_runs` prompt is the permanent path |
| Sporting Life Cloudflare challenge | No prices from that retailer | **Accepted** — paid bypass declined on principle |
| Sport Experts custom platform | No prices | Open, low priority ("future") |
| COROS MCP OAuth is desktop-managed | Son of Anton can't sync COROS directly; needs Claude Desktop as mediator | **Accepted** — encoded in the agent-prompt design |

---

## 9. Recent Architectural Decisions

Last ~10 days, newest first (full record: `docs/design_decisions.md`):

-4. **E8 — in-process rate limit on `POST /api/chat/message`** (2026-07-08, Session J — 🕐 Keep for now). A token-bucket limiter (`services/rate_limit.py`), keyed per client IP, returns 429 + `Retry-After` when a client exceeds the rate (default 20/min, env-tunable); it completes the R2.1 spend story — R2.1 stopped *anonymous* spend, this stops an *authenticated* client looping and burning paid credits. In-process by design (single-process assumption, D4/E5), not a security boundary (auth E7 is). Revisit a shared store / eviction only with a second worker or remote clients (R5.2).
-3. **R2.2 — Alembic is the sole schema authority** (2026-07-07, Session E — A6 → Superseded). Startup runs `alembic upgrade head` (`database.run_migrations()`) instead of `create_all`, which is now test-fixture-only; the baseline revision recreates the exact pre-Alembic schema so a fresh DB builds from Alembic alone (verified table-for-table; round-trips to base); `legacy_migrations/` deleted; live DB + backups moved to `~/anton-data/` with a dated-backup convention. The "model edit without migration silently diverges" trap is closed. The remaining ⚠️ scheduled-to-change decision is now just **C8** (chat memory).
-2. **R2.1 — bearer-token auth on all surfaces** (2026-07-07, Session D — E1 → Superseded by **E7**). One shared secret (`ANTON_SECRET`) gates `/api/*` and `/mcp` via a pure-ASGI middleware (constant-time compare, 401 empty body, exempts `/`+health+OPTIONS); default bind `127.0.0.1`; fail-fast on missing secret. SPA sends it (axios interceptor + the raw chat `fetch`/scrape-SSE paths — the scrape stream was moved off `EventSource` to a `fetch` reader to carry the header); Claude Desktop via `mcp-remote --header`; the loopback client at connect time (scoped, so no leak to external MCP servers). The remaining ⚠️ scheduled-to-change set is now just **A6** (schema authority) and **C8** (chat memory). Rate limiting on `/api/chat/message` stays a separate R2 item.
-1. **Mileage ledger enforced at the schema boundary** (2026-07-07, Session C — C1 fix) — `current_mileage`/`starting_mileage` removed from `OwnedShoeUpdate`; the only way to override the counter is now the sanctioned `rotation.adjust_mileage()` (`POST /owned-shoes/{id}/adjust-mileage`), which journals the drift. INV-1 moves from "convention + one known breach" to structurally enforced. Same session: M3 scrape-lock wedge closed (whole `run_scrape_job` body under the lock-releasing `finally`; admin force-release endpoint), and `SECURITY_PASS_PLAN.md` written to gate R2.1. **These stay unauthenticated for now under E1**; R2.1 gates the new admin endpoint.
0. **D7 and E5 executed** (2026-07-07) — the `scraper_manager` shim was **deleted** (D7 → Superseded) and the unused **APScheduler** dependency **removed** (E5 → Superseded). Both flipped from the ⚠️ scheduled-to-change set to the Superseded table. The remaining ⚠️ set is A6 (schema authority), C8 (chat memory), E1 (auth).
1. **MSRP drives deals (B9-v2)** (2026-07-06) — a deal is any price strictly below MSRP; savings measured against MSRP; `target_price` optional/nullable. Migration `d4e5f6a7b8c9`; design_decisions B9 → Superseded, B9-v2 + B8 amended same day.
2. **Canonical `activities` table; `shoe_runs` → attribution with property proxies** (2026-07-04) — B4/B5. Also set the migration-discipline precedent (E4: reversible, backed-up, reconciled).
3. **Shared retirement-pipeline computation** (2026-07-04) — Home alerts became a projection over `rotation.retirement_pipeline`; Home and `/shoes` structurally cannot disagree.
4. **Home as one-round-trip attention surface** (2026-07-03) — `GET /api/home` under a <200 ms budget, explicitly the future mobile launch screen.
5. **Old Dashboard removed** (2026-07-03) — `/` renders Home; `useDashboardStats` survives only for Layout/Settings.
6. **Diamond nav dots kept despite the new brand mark** (2026-07-04) — functional motif ≠ logo; small but shows the design-token discipline.
7. Standing from earlier phases but load-bearing daily: one write path for runs (B7), confirmation gates on AI writes (C9), API-first numbers (A4).

---

## 10. Current Branch Assumptions

- **HEAD is on `main`** (`.git/HEAD` verified). No long-lived branches are part of the workflow.
- **Convention** (REDESIGN_PLAN.md §5): one phase per Claude Code session; one commit per numbered task with phase-prefixed conventional messages (`p5: canonical activities migration`); backend endpoints land *with tests* before their consuming UI task; every phase ends suite-green + desktop & ~380 px visual pass.
- **Unverified from this audit:** ~~working-tree cleanliness. The `docs/` files generated by the documentation program (and this file) are likely **uncommitted** — commit them as a docs batch.~~ Resolved 2026-07-06: the batch is committed (R1.1). The `.bak*` DB files were checked against `.gitignore` the same session — `backend/.gitignore` ignores `*.db` and the root ignores `*.db.bak*`; nothing DB-related can be committed.
- The live SQLite DB sits in the tree; treat `main` + the DB file as jointly constituting "production."

---

## 11. Areas Requiring Immediate Attention

Ordered; "immediate" means *next few sessions*, not emergencies — nothing is on fire. **R1 done; C1/M3 safety fixes done; R2.1 (security) + R2.2 (schema authority) shipped and now *live*; R2.7 (training depth) complete end-to-end (T1–T8); R2.3 (indexed reads + watchlist service) shipped; chat rate limiting shipped (E8).** The active R2 thread is now R2.4–R2.6.

1. **R2.4 shoe-type controlled vocabulary** — promote `shoe_type` from free strings to a backend-owned served list (the pattern R2.7 T1's `activity_tag` vocabulary already established), deleting `lib/shoeTypes.js` as an independent copy.
2. **R2.5 scrape observability** — persist per-retailer scrape runs/attempts (started/finished/count/error), surface health + trend in Settings. The substrate R4.1 scheduling + R4.5 watchdog require.
3. **R2.6 server-side chat/memory persistence** — move Son of Anton conversations + checkpoint state off localStorage into the backend (design_decisions C8, the last ⚠️ scheduled-to-change item).
4. **Deal-domain test gaps**: retirement/requalification, the orphan guard + its H2 partial-failure gap, promo manual-beats-scraped (refactor.md H1/H2).
5. **Provider agentic-loop consolidation** (tech_debt 5.2) — the model-catalog half is done (R1.5d); collapse the 3× loop **before** the R3 agents extend it.
6. **Optional follow-ons:** the watchlist reduction still reduces in Python inside `services/watchlist.py` (labelled O(N), fine); `deals`/`dashboard` fat routers remain to be thinned like watchlist was; surface the chat 429 as a client-side toast; consider throttling `POST /api/chat/resource/read` too.

---

*Maintenance note: this file describes 2026-07-07 and decays fastest of all the docs. Update the Snapshot date, §2 table, §9, and §11 at session end; move shipped items from §4/§5 into §3. When in doubt, the `docs/changelog.md` top entries are the source of truth for what happened; this file is the source of truth for what it means.*
