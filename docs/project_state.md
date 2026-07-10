# Anton — Project State

**Snapshot date:** 2026-07-10 (after R3.6 session — Race-block training advisor: `services/race_advisor.py` + `get_race_block_context` MCP tool + `race_block_advisor` MCP prompt; suite 282 → **298** (+14 new tests). Prior: R3.3 — Shoe Review Pipeline; R3.2 — Deal Alert Agent; R3.4 — MCP watchlist parity + resource expansion; R3.1 — Weekly Rotation Summary Agent; debt-sweep — fat router extraction + chat 429 toast; **All of R2 + RA1.0–RA1.4 (code) + R3.1–R3.4 + R3.6 are now shipped; RA1.5 cutover is next; R4.1 (Scheduled scraping) is the next code task.**)
**Read this first, then:** `docs/ai_context.md` → `docs/architecture.md` → `docs/domain_model.md`. This file is the *perishable* one — it describes a moment, and staleness here is expected and fixable; update it at the end of every working session.

---

## 1. Sixty-Second Summary

Anton (repo name: `running-shoe-deals`) is a **single-user personal running platform**: shoe-deal watching across 8 Canadian retailers + a canonical run/training history + shoe rotation wear tracking, with an embedded AI assistant (Son of Anton) and a full MCP server used by Claude Desktop. FastAPI + SQLite + React SPA, all local, no auth (deliberate, deferred).

**Where things stand right now:** the multi-phase **Anton redesign is functionally complete** — all five tabs (Home / Training / Shoes / Deals / Son of Anton) are built. The most recent R3 work: R3.6 race-block training advisor shipped 2026-07-10 — `services/race_advisor.py` + `get_race_block_context` MCP tool + `race_block_advisor` MCP prompt; suite 282 → **298**. Prior: R3.3 shoe review pipeline; R3.2 — Deal Alert Agent; R3.4 — MCP watchlist parity + resource expansion; R3.1 — Weekly Rotation Summary Agent. **Documentation program** (`documentation_creation.md`) is **complete and committed** (R1.1, 2026-07-06). **All of R2 and RA1.0–RA1.4 (code) and R3.1–R3.4 + R3.6 are shipped.** RA1.5 (cutover) is the next human task; R4.1 (Scheduled scraping) is the next code task (R3.5 notification channel explicitly deferred — see roadmap).

**The stated Current Focus** (per `docs/changelog.md`): *"Product images, colorway consolidation, scraper durability + coverage."* Note: images/colorways largely shipped in June — read this focus line as the *durability/polish pass* over those features plus scraper coverage, not greenfield work. (If that reading is wrong, correct this line.)

---

## 2. Current Development Status

| Track | Status |
|---|---|
| Anton redesign Phases 1–4 (IA, Deals watchlist, Training tab, Home) | ✅ Complete (Phase 4 landed 2026-07-03) |
| Phase 5 backlog | 🟡 3 of 4 items done (canonical activities ✅ 2026-07-04 · `/shoes` lifecycle reframe ✅ · app mark ✅ · **agents remaining**) |
| Strava historical import (694-run, 8-year archive) | ✅ Complete and now *structurally* permanent (absorbed into `activities`) |
| Test suite | ✅ **298 passing**, 34 modules (R3.6: `test_race_advisor.py` new +14; R3.3: `test_shoe_review.py` new +7; R3.2: `test_deal_alerts.py` new +22 + 2-test discrepancy from R3.4 resolved; R3.4: stable at 251; R3.1: `test_weekly_summary.py` new +20; RA1.4: stable; RA1.3: `test_access_log.py` new +15; `test_auth.py` +5; `test_oauth.py` +3; net +23; RA1.1b: `test_oauth.py` new +18; `test_auth.py` −4 capability-URL tests; net +14; RA1.2: stable; RA1.1: `test_auth.py` rewritten +8 net; R2.7.2: `test_races.py` +2; Session Q: +3; Session O: +13; Session N: +15; Session M: +9; Session L: +8; Session K: +8; Session J: +5; earlier sessions: see prior entries) |
| RA1.4 — Backups off-laptop | ✅ **Code shipped** (2026-07-09) — Litestream config (`backend/litestream.yml`; B2/S3-compatible; 14-day WAL retention + daily snapshots); `backend/entrypoint.sh` (restore-on-start + `litestream replicate -exec uvicorn`; falls back to plain uvicorn without `LITESTREAM_BUCKET`); Dockerfile installs Litestream v0.3.13 (arch-aware) + sqlite3 CLI; `deploy/restore.sh` (drill + disaster recovery); `deploy/pull-snapshot.sh` (laptop dev-DB seed). Suite stable at 231. **Human steps remaining before RA1.4 is fully done:** (1) provision B2 bucket + fill in `LITESTREAM_*` vars in production `.env`; (2) run restore drill (`deploy/restore.sh` to scratch path, verify 933+ activity count); (3) pull laptop snapshot after RA1.5 cutover. |
| RA1.3 — Surface & abuse hardening | ✅ **Shipped** (2026-07-09) — `AccessLogMiddleware` (one structured log line per request: method/path/client/status/duration_ms; no request headers; query-param credential redaction for `code`/`state`/`access_token`/`token`/`refresh_token`); per-IP auth-failure rate limiter (429 + `Retry-After` after burst; `AUTH_FAILURE_LIMIT_PER_MINUTE` env); 401 logged at WARNING with source IP; login-page rate limiter (every POST consumes a token; `LOGIN_FAILURE_LIMIT_PER_MINUTE` env); Caddyfile comment updated. Two `ra1:` commits. Suite 210 → 231. **Remaining acceptance criterion (human step):** set up external uptime pinger on `/health` before RA1.5 cutover. |
| Documentation program | ✅ **Complete and committed** (R1.1, 2026-07-06) — full `docs/` suite + `CLAUDE.md` (incl. §14 INVARIANTS) + `refactoring/` + final review + reconciliation + `.claude/skills/` (13 workflow skills) |
| Roadmap R1 (loose ends) | ✅ **Complete** (2026-07-07) — R1.1/R1.2 docs, R1.3 replacement-deals card, R1.4 proxy guards, R1.5 debt sweep (Task D · shim delete · pure `pace` · chat catalog), R1.6 APScheduler removed |
| Review safety fixes (C1 / M3) | ✅ **Resolved** (Session C, 2026-07-07) — mileage ledger no longer writable via PUT (sanctioned `adjust_mileage` path); scrape-lock wedge closed + admin force-release/status endpoints |
| Security pass (R2.1) | ✅ **Shipped** (Session D, 2026-07-07) — shared bearer token on `/api`+`/mcp` (pure-ASGI middleware), `127.0.0.1` default bind, fail-fast on missing secret, SPA + Desktop + loopback all send the token, 13 HTTP-layer tests. E1 → Superseded by E7. **Live activation (set `.env` secret, update Desktop `--header`, restart) is a human step** — `CLAUDE_DESKTOP_SETUP.md`. Rate limiting is a separate R2 item. |
| Schema authority (R2.2) | ✅ **Shipped** (Session E, 2026-07-07) — Alembic sole source: startup runs `alembic upgrade head` (`database.run_migrations()`), `create_all` demoted to test fixtures, baseline revision recreates the pre-Alembic schema (fresh DB builds from Alembic alone), `legacy_migrations/` deleted, live DB + backups moved to `~/anton-data/`. A6 → Superseded. **Server restart needed** to pick up the new `DATABASE_URL` (pairs with the R2.1 restart). |
| Chat & memory persistence (R2.6) | ✅ **Shipped** (Session M, 2026-07-08) — conversations + checkpoint-prompt state moved off localStorage into `chat_conversations` + `checkpoint_prompts` (migration `e1f2a3b4c5d6`); `services/chat_history` + `services/checkpoints`; REST CRUD (`/api/chat/conversations`, `/api/checkpoint-prompts`); frontend on React Query. Streaming endpoint stays stateless. Start-fresh (no localStorage migration); MCP exposure deferred to R3. **C8 → Superseded by C10; the ⚠️ scheduled-to-change list is now empty.** Live browser visual pass pending (dev backend was down this session). |
| Scrape observability (R2.5) | ✅ **Shipped** (Session L, 2026-07-08) — durable `scrape_runs` per retailer per attempt (migration `d0e1f2a3b4c5`), written only by `ScrapeOrchestrator.scrape_retailer`; `services/scrape_history` health derivation; `GET /api/scrape/history` + MCP `scrape_health` + Settings "Retailer health" card. D8 recorded; D4 single-process lock deliberately unchanged (R4.1 forces that, not R2.5). Verified live end-to-end (run stamped `running` mid-flight → `success`). |
| Training depth (R2.7) | ✅ **Complete** (Sessions 1–3: F/G/H, 2026-07-07→08) — T1 tag vocabulary + 4 `activities` columns · T2 COROS field population · T3 PB eligibility fix · T4a month volume axis · T4b date-range picker · T5 `athlete_metrics` + fitness card · T6 `/activities/:id` edit + reassignment + race promotion · T7 `planned_races.activity_id` link · T8 COROS-name tag inference. Migrations `e5f6a7b8c9d0`, `f6a7b8c9d0e1`, `a7b8c9d0e1f2`. B15/B16 added. |
| RA1.0 + RA1.1 — Auth v2 (named-token map + capability-URL) | ✅ **Shipped** (2026-07-09) — S1–S3 spikes; D0 = cloud VM; `ANTON_TOKENS`; `ANTON_SECRET` rotated; capability-URL shipped dark; E7 → E9. Suite 188 → 194. |
| RA1.1b — OAuth 2.1 connector auth | ✅ **Shipped** (2026-07-09) — Path 1 chosen; `AntonOAuthProvider` (9 async methods); `oauth_auth_codes` + `oauth_tokens` tables (migration `0b1c2d3e4f5a`); login page; capability-URL deleted; 18 new tests. Suite 194 → 210. E9 updated; capability-URL → Superseded. |
| RA1.2 Deployment substrate | ✅ **Shipped** (2026-07-09) — `backend/Dockerfile` (Python 3.11-slim + Playwright/Chromium + `--workers 1`); `backend/.dockerignore`; `docker-compose.yml` (loopback-only port + data volume + healthcheck); `deploy/Caddyfile` (TLS + `flush_interval -1` + credential-redacting log filter); `deploy/.env.production.example`; **INV-9** in CLAUDE.md §14. Remaining acceptance criteria (deployed HTTPS + streaming verified through proxy) = human steps at RA1.5. |

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
- **Scrape observability (R2.5)** — durable `scrape_runs` (per retailer per full-catalog attempt: status/counts/error), written only by `ScrapeOrchestrator.scrape_retailer`; read-time health (`ok`/`warning`/`error`/`unknown`) via `services/scrape_history`; `GET /api/scrape/history` + MCP `scrape_health` + Settings → Sync "Retailer health" card. Migration `d0e1f2a3b4c5` (2026-07-08).
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
- MCP server: ~22 tools, 10 resources (markdown+JSON), `sync_coros_runs` prompt, `sync_fitness` prompt, `weekly_rotation_summary` prompt (R3.1), sampling-powered `draft_shoe_review`; mounted at `/mcp` with lifespan-merged session manager.
- Son of Anton: multi-provider (Anthropic/OpenAI/Gemini) streaming agentic chat, auto tool discovery via loopback MCP, resource pre-priming, @-mention resource picker, localStorage conversations.
- **Weekly Rotation Summary Agent (R3.1, 2026-07-10):** `services/weekly_summary.py` compiles the ISO-week digest — volume vs last week, per-shoe usage (km-descending + shoe_type), retirement pipeline, notable runs (Race/Parkrun/Intervals/Tempo/Long Run/Track), 100km checkpoints, next race. Exposed as `get_weekly_summary` MCP tool + `weekly_rotation_summary` MCP prompt. Read-only; no confirmation gate. 20 new tests.
- **Race-block training advisor (R3.6, 2026-07-10):** `services/race_advisor.py` assembles `RaceBlockContext` — soonest upcoming race (countdown/distance/target pace), last 12 weeks of weekly volume (avg computed), retirement pipeline with shoe_type, latest fitness snapshot (VO2 max, threshold pace, race predictions). Exposed as `get_race_block_context` MCP tool + `race_block_advisor` MCP prompt. Advisory observations only — no plan generation; no confirmation gate. 14 new tests.
- **MCP watchlist parity + resource expansion (R3.4, 2026-07-10):** `get_watchlist` MCP tool (thin adapter over `watchlist_svc.build_watchlist`; on-sale first, then watching A-Z; exposes best_deal, best_ever_price, last_seen per retailer); `deals://watchlist` resource; `training://summary` resource (last 12 weeks weekly); `training://fitness` resource (latest AthleteMetric snapshot). No new tests (thin adapters over already-tested service layer).
- **Deal Alert Agent (R3.2, 2026-07-10):** `services/deal_alerts.py` detects three alert types since a reference timestamp — new active deals (sorted by savings %), price drops on pre-existing active deals (sorted by drop amount), and replacement candidates for pipeline shoes (≥ 75% mileage limit) via shoe_type cross-domain heuristic. `since=None` defaults to a 7-day first-run window. `get_deal_alerts` MCP tool reads `last_deal_alert_check_at` from `AppSettings`, calls the service, advances the high-water mark, and returns the full digest. `deal_alert_digest` MCP prompt drives the structured briefing workflow. 22 new tests in `test_deal_alerts.py`.
- **Shoe Review Pipeline (R3.3, 2026-07-10):** `review_draft` nullable Text column on `owned_shoes` (migration `a2b3c4d5e6f7`); `rotation.store_shoe_review()` — the single write path (overwrites previous draft). `PATCH /api/owned-shoes/{id}/review` REST adapter; `review_draft` exposed in `OwnedShoeResponse` so `GET /api/owned-shoes/{id}` also returns it. `draft_shoe_review` auto-saves after sampling. `save_shoe_review` MCP tool for runner-edited saves. `retire_shoe` MCP tool now includes `review_prompt` when the shoe has logged notes. `shoes://review/{id}` MCP resource returns the stored draft or a "no review yet" hint. 7 new tests in `test_shoe_review.py`.

**Engineering**
- 2026 refactor: services extraction, scraper decomposition (orchestrator/registry/deal-store/lock), Alembic adoption; Strava import pipeline with self-checking assumptions.
- **Documentation program shipped and committed (R1.1, 2026-07-06):** full `docs/` suite, `refactoring/` reviews, `CLAUDE.md` (with the §14 INVARIANTS checkable list, INV-1…INV-8), the `claude.md → docs/changelog.md` rename, and the `.claude/skills/` library (13 workflow skills per `docs/skills_library.md`; the `shoe_type` vocabulary table landed in domain_model §4.3 the same session).
- **Schema authority resolved (R2.2, Phase 2 Session E, 2026-07-07):** Alembic is the sole schema source — startup runs `alembic upgrade head` (`database.run_migrations()`) instead of `create_all` (now test-fixture-only); the baseline revision `cf1eccba0a79` recreates the exact pre-Alembic schema so a fresh DB builds from Alembic alone; `legacy_migrations/` deleted; the live DB + backups moved out of the repo tree to `~/anton-data/`. A6 → Superseded.
- **R1 debt sweep (Phase 2 Session B, 2026-07-07):** `ShoeRun.activity` eager-loaded at all five run-list seams (R1.4); `rotation.attach_computed_fields` extracted, killing the last router→router import (R1.5a); `scraper_manager` shim deleted, consumers on `ScrapeOrchestrator`/`lock`/`registry` (R1.5b); pure `app/utils/pace.py` replacing three copies (R1.5c); `chat_service.MODELS` single-sourcing the model catalog + id-based provider routing (R1.5d); APScheduler removed from `requirements.txt` (R1.6). D7 and E5 → Superseded.

**Engineering (cont.)**
- **Shoe-type controlled vocabulary (R2.4, Session K, 2026-07-08):** `shoe_type` promoted from free strings to a backend-owned vocabulary (`app/utils/shoe_types.py`, the cross-domain join key) served at `GET /api/shoe-types` and validated on write (422 on off-vocab) — mirrors R2.7 T1's `activity_tag`. The frontend `lib/shoeTypes.js` vocabulary copy is deleted (reduced to presentation-only colours + a title-case formatter); forms/badges/filters fetch via `useShoeTypes()`. Migration `c9d0e1f2a3b4` normalized 9 legacy `owned_shoes` free-text values (E4-reconciled, per-shoe Race Shoe split confirmed with the runner).
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
- ~~**Fat legacy routers** (`watchlist`, `deals`, `dashboard`) with inline ORM logic~~ — `watchlist` extracted (R2.3, 2026-07-08); `deals` → `services/deals.py` and `dashboard` → `services/dashboard.py` extracted (2026-07-10); MCP `get_deals`/`get_shoe_deals` now call the same service (REST/MCP parity). `watchlist` reduction O(N) Python remains in `services/watchlist.py` (labelled, fine at scale).
- ~~**Whole-table in-Python reads** (`unified_activities`, watchlist reduction)~~ — `unified_activities` is now a single indexed SQL query (R2.3, Session I; index `ix_activities_type_run_date`). Watchlist reduction labelled O(N), fine at scale.
- ~~**Provider agentic loop implemented 3×**~~ — resolved 2026-07-10 (tech_debt P1-8): `BaseLLMProvider.run()` owns the shared loop; 5 abstract methods per provider.
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

-10. **R3.3 — one review per shoe; overwrite semantics** (2026-07-10 — ✅ Keep). `review_draft` is a single nullable Text column on `owned_shoes`. `rotation.store_shoe_review` unconditionally overwrites — no version history, no append. Rationale: a review is a living document the runner refines until it's done; the notes journal is the append-only record; storing review versions would duplicate that concern. Exportable via `shoes://review/{id}` resource.
-9. **R3.2 — deal alert high-water mark via existing `AppSettings` table** (2026-07-10 — ✅ Keep; reuses the pattern from `last_coros_sync_at`). `last_deal_alert_check_at` stored as a naive-UTC ISO string in `AppSettings` (key/value). The MCP tool strips tzinfo before passing to the service to satisfy SQLite's naive-datetime comparisons. No migration needed — `AppSettings` already exists and is append-at-need. First call without a key → 7-day default window. Caller (the tool) owns the watermark; service is purely functional.
-8. **RA1.3 — in-process per-IP rate limiters for auth & login** (2026-07-09 — ✅ Keep for now; extends E8). Two new `KeyedRateLimiter` instances in `services/rate_limit.py`: `auth_failure_limiter` (per-IP token bucket; exhaustion → 429 + `Retry-After` on bearer-auth failures; `AUTH_FAILURE_LIMIT_PER_MINUTE` / `AUTH_FAILURE_BURST` env — default 10/min) and `login_failure_limiter` (per-IP, every `/oauth/login` POST consumes a token; `LOGIN_FAILURE_LIMIT_PER_MINUTE` / `LOGIN_FAILURE_BURST` — default 5/min). In-process by design (same D4/E8 single-process reasoning — INV-9). Revisit at RA1.5 if multi-worker ever required.
-7. **E9 — named per-client bearer tokens + OAuth 2.1 connector auth** (RA1.1 + RA1.1b, 2026-07-09 — E7 → 🔁 Superseded). RA1.1: `ANTON_TOKENS="name:token,..."` (desktop / loopback / spa each revocable independently); constant-time multi-token comparison without short-circuiting; old `ANTON_SECRET` rotated. RA1.1b: Path 1 chosen — `AntonOAuthProvider` (9 async methods, `mcp.server.auth.provider` Protocol); `create_auth_routes()` wires 4 OAuth endpoints; `/oauth/login` password gate; `oauth_auth_codes` + `oauth_tokens` tables; capability-URL deleted. See E9 in design_decisions.md for the full RA1.1b detail.
-6. **D0 — hosting decision: cloud VM for RA1** (2026-07-09, RA1.0 research — `REMOTE_ACCESS_PLAN.md` §4). Option A: Hetzner CX22 / Fly.io Shared-CPU-1x (~$5–8 CAD/mo), standard datacenter IP. Always-on home box is the documented escape hatch if DC-IP scrape degradation is observed at RA1.5 (measured via R2.5 `scrape_runs`; no paid bypass — D3 stands).
-5. **C10 — server-side chat & memory persistence** (2026-07-08, Session M — ✅ Keep; **C8 → 🔁 Superseded**). Conversations + checkpoint-prompt state moved off localStorage into `chat_conversations` + `checkpoint_prompts` (migration `e1f2a3b4c5d6`); message arrays stored as JSON columns; client-UUID PK; streaming endpoint stays stateless. Start-fresh; MCP exposure deferred to R3. **Last ⚠️ scheduled-to-change decision** — that to-do list is now empty.
-4. **E8 — in-process rate limit on `POST /api/chat/message`** (2026-07-08, Session J — 🕐 Keep for now). Token-bucket limiter (`services/rate_limit.py`), per client IP, 429 + `Retry-After`; completes the R2.1 spend story (E7 stopped anonymous spend, E8 stops an authenticated loop). In-process by design (D4/single-process). Revisit with a second worker or remote clients (R5.2).
-3. **R2.2 — Alembic is the sole schema authority** (2026-07-07, Session E — A6 → Superseded). Startup runs `alembic upgrade head`; `create_all` is test-fixture-only; baseline revision recreates the exact pre-Alembic schema; `legacy_migrations/` deleted; DB + backups moved to `~/anton-data/`.
-2. **R2.1 — bearer-token auth on all surfaces** (2026-07-07, Session D — E1 → Superseded by **E7** → now Superseded by **E9**). The shared-secret era; SPA baked `VITE_ANTON_SECRET`, Claude Desktop used `mcp-remote --header`, loopback injected at connect time. Superseded 2026-07-09.
-1. **Mileage ledger enforced at the schema boundary** (2026-07-07, Session C — C1 fix). `current_mileage`/`starting_mileage` removed from `OwnedShoeUpdate`; sanctioned `rotation.adjust_mileage()` path only.
0. **D7 and E5 executed** (2026-07-07) — `scraper_manager` shim deleted; APScheduler removed.
1. **MSRP drives deals (B9-v2)** (2026-07-06). Migration `d4e5f6a7b8c9`.
2. **Canonical `activities` table; `shoe_runs` → attribution with property proxies** (2026-07-04) — B4/B5; E4 migration precedent.
3. **Shared retirement-pipeline computation** (2026-07-04) — Home alerts a projection over `rotation.retirement_pipeline`.
4. **Home as one-round-trip attention surface** (2026-07-03) — `GET /api/home` <200 ms budget.
5. **Old Dashboard removed** (2026-07-03).
6. **Diamond nav dots kept despite rebrand** (2026-07-04).
7. Standing from earlier phases but load-bearing daily: one write path for runs (B7), confirmation gates on AI writes (C9), API-first numbers (A4).

---

## 10. Current Branch Assumptions

- **HEAD is on `main`** (`.git/HEAD` verified). No long-lived branches are part of the workflow.
- **Convention** (REDESIGN_PLAN.md §5): one phase per Claude Code session; one commit per numbered task with phase-prefixed conventional messages (`p5: canonical activities migration`); backend endpoints land *with tests* before their consuming UI task; every phase ends suite-green + desktop & ~380 px visual pass.
- **Unverified from this audit:** ~~working-tree cleanliness. The `docs/` files generated by the documentation program (and this file) are likely **uncommitted** — commit them as a docs batch.~~ Resolved 2026-07-06: the batch is committed (R1.1). The `.bak*` DB files were checked against `.gitignore` the same session — `backend/.gitignore` ignores `*.db` and the root ignores `*.db.bak*`; nothing DB-related can be committed.
- The live SQLite DB sits in the tree; treat `main` + the DB file as jointly constituting "production."

---

## 11. Areas Requiring Immediate Attention

Ordered; "immediate" means *next few sessions*, not emergencies — nothing is on fire. **All of R2 (2.1–2.7) + R2.7.1 + R2.7.2 + RA1.0 + RA1.1 + RA1.1b + RA1.2 + RA1.3 + RA1.4 (code) + R3.1 + R3.2 + R3.3 + R3.4 + R3.6 are now shipped.** Suite: **298 passing**. RA1.5 cutover is the blocking human task; R4.1 is the next code task.

0. ~~**RA1.1b**~~ ✅ **Done (2026-07-09)** — OAuth 2.1 (`AntonOAuthProvider` + login page + 18 tests, capability-URL deleted). Suite 194 → 210.
0. ~~**RA1.3**~~ ✅ **Done (2026-07-09)** — Auth-failure 401 logging + per-IP rate limiter (429) + `AccessLogMiddleware` (structured per-request log + credential redaction) + login-page rate limiter + Caddyfile comment. Suite 210 → 231.
0. ~~**RA1.4**~~ ✅ **Code done (2026-07-09)** — Litestream config + `entrypoint.sh` + Dockerfile install + restore drill script + pull-snapshot script. Suite stable at 231. **Three human steps before RA1.4 is fully done:** (1) provision B2 bucket + set `LITESTREAM_*` vars; (2) run `deploy/restore.sh` to scratch path + verify 933+ activities; (3) set up uptime pinger on `/health`. All three execute at/before RA1.5 cutover.
0. ~~**R3.1 Weekly Rotation Summary Agent**~~ ✅ **Done (2026-07-10)** — `services/weekly_summary.py` + `get_weekly_summary` MCP tool + `weekly_rotation_summary` MCP prompt. Suite 231 → 275 (with R3.2 resolving the 2-test discrepancy). Backend restart needed to pick up the new service import.
0. ~~**R3.4 — MCP watchlist parity**~~ ✅ **Done (2026-07-10)** — `get_watchlist` MCP tool + `deals://watchlist` resource + `training://summary` resource + `training://fitness` resource. Suite stable at 251 at time of shipping. Backend restart needed to pick up the changes.
0. ~~**R3.2 — Deal Alert Agent**~~ ✅ **Done (2026-07-10)** — `services/deal_alerts.py` (new deals / price drops / replacement alerts, functional service with injectable clock) + 22 tests + `get_deal_alerts` MCP tool (AppSettings high-water mark, advances on every call) + `deal_alert_digest` MCP prompt. Suite 251 → 275.
0. ~~**R3.3 — Shoe review pipeline maturation**~~ ✅ **Done (2026-07-10)** — `review_draft` column (migration `a2b3c4d5e6f7`) + `rotation.store_shoe_review()` + `PATCH /api/owned-shoes/{id}/review` + `save_shoe_review` MCP tool + `shoes://review/{id}` resource + `retire_shoe` review nudge. Suite 275 → 282. Backend restart needed to pick up the new tool + resource.
1. **RA1.5 — Cutover & validation** — provision host, deploy container, E4 count reconciliation, re-point Claude Desktop, add claude.ai connector; two exit criteria: mobile sync E2E on cellular + DC-IP scrape comparison via R2.5 `scrape_runs`. **Also during RA1.5:** restore drill + uptime pinger (RA1.3/RA1.4 remaining human steps). `REMOTE_ACCESS_PLAN.md` §6/§7 is the runbook.
2. **R4.1 — Scheduled scraping** — leads R4; no R3.5 dependency; fully unblocked. Needs a real design: persisted job state, DB-level coordination replacing the in-memory scrape lock, per-retailer staggering, failure recording into R2.5's tables. Write `SCHEDULED_SCRAPING_PLAN.md` before code.
3. ~~**R3.5 — Notification channel**~~ ⏸ **Deferred** — pull-based MCP tools (R3.1/R3.2/R3.6) already cover the on-demand surface; push delivery revisit trigger: when R4.2/R4.3/R4.5 surface a felt need for unattended delivery. See roadmap R3.5 deferral note.
4. ~~**R3.6 — Race-block training advisor**~~ ✅ **Done 2026-07-10** — `services/race_advisor.py` + `get_race_block_context` tool + `race_block_advisor` prompt; 14 tests; suite 282 → 298.
5. ~~**Provider agentic-loop consolidation** (tech_debt 5.2)~~ ✅ **Done 2026-07-10** — `BaseLLMProvider.run()` owns the shared loop; 5 abstract methods per provider; `_ToolCall` dataclass; suite stable at 231. Backend restart needed to pick up the change.
6. **Optional follow-ons:** the shoe-major synchronous scrape doesn't yet emit R2.5 `scrape_runs` (deliberate deferral, D8); watchlist reduction still O(N) Python in `services/watchlist.py` (labelled, fine). ~~`deals`/`dashboard` fat routers remain~~ ✅ Done 2026-07-10. ~~surface chat 429 as client-side toast~~ ✅ Done 2026-07-10.

---

*Maintenance note: this file describes 2026-07-10 (R3.3 Shoe Review Pipeline) and decays fastest of all the docs. Update the Snapshot date, §2 table, §9, and §11 at session end; move shipped items from §4/§5 into §3. When in doubt, the `docs/changelog.md` top entries are the source of truth for what happened; this file is the source of truth for what it means.*
