# Anton — Project State

**Snapshot date:** 2026-07-06 (evening — after the `msrp_drives_deals` migration and the docs-reconciliation session).
**Read this first, then:** `docs/ai_context.md` → `docs/architecture.md` → `docs/domain_model.md`. This file is the *perishable* one — it describes a moment, and staleness here is expected and fixable; update it at the end of every working session.

---

## 1. Sixty-Second Summary

Anton (repo name: `running-shoe-deals`) is a **single-user personal running platform**: shoe-deal watching across 8 Canadian retailers + a canonical run/training history + shoe rotation wear tracking, with an embedded AI assistant (Son of Anton) and a full MCP server used by Claude Desktop. FastAPI + SQLite + React SPA, all local, no auth (deliberate, deferred).

**Where things stand right now:** the multi-phase **Anton redesign is functionally complete** — all five tabs (Home / Training / Shoes / Deals / Son of Anton) are built. The two most recent structural events: the canonical `activities` table (2026-07-04, reversible reconciled migration) and **MSRP-drives-deals** (2026-07-06 — deal qualification and savings now measured against MSRP; `target_price` demoted to an optional threshold; migration `d4e5f6a7b8c9`). The suite is green at **64 tests**. What remains of Phase 5 is the agent work (Deal Alert / Weekly Rotation Summary) and durability items. The **documentation program** (`documentation_creation.md`) is **complete**: all content prompts + the final review (`docs/documentation_review.md`) + the 2026-07-06 docs-reconciliation pass — the suite is ready to be the primary context for future sessions; committing it is the outstanding step.

**The stated Current Focus** (per `docs/changelog.md`): *"Product images, colorway consolidation, scraper durability + coverage."* Note: images/colorways largely shipped in June — read this focus line as the *durability/polish pass* over those features plus scraper coverage, not greenfield work. (If that reading is wrong, correct this line.)

---

## 2. Current Development Status

| Track | Status |
|---|---|
| Anton redesign Phases 1–4 (IA, Deals watchlist, Training tab, Home) | ✅ Complete (Phase 4 landed 2026-07-03) |
| Phase 5 backlog | 🟡 3 of 4 items done (canonical activities ✅ 2026-07-04 · `/shoes` lifecycle reframe ✅ · app mark ✅ · **agents remaining**) |
| Strava historical import (694-run, 8-year archive) | ✅ Complete and now *structurally* permanent (absorbed into `activities`) |
| Test suite | ✅ 64 passing, 12 modules (`test_deals.py` added 2026-07-06 with the MSRP rules; count dropped from 69 to 61 when backfill tests retired, back up since) |
| Documentation program | ✅ **Complete** — full `docs/` suite + `CLAUDE.md` + `refactoring/` + final review (`docs/documentation_review.md`) + docs-reconciliation pass (2026-07-06). Outstanding: **commit the batch** (R1.1); then Phase 2 (implementation planning) may begin |
| Security pass | ⛔ Not started — explicitly deferred; the gate for any exposure-increasing feature |

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

---

## 4. Features Partially Complete

| Item | State | The missing piece |
|---|---|---|
| **Replacement Deals card on `/shoes/:id`** | Explicit "Coming soon" placeholder since 2026-06-24 | The *data* now exists (pipeline computation + deal counts shipped 2026-07-04) — the detail-page card was never wired to it. Verify current state before building; may be a small task now. |
| **Server-side COROS sync** | Code complete (`coros_client`, `coros.py`, REST endpoints), cleanly disabled | COROS won't issue Open-API credentials to individuals. Dormant by decision (design_decisions.md C6); revives only if COROS opens access. |
| **Anton rebrand** | UI, mark, favicon done | Repo name, API title ("Running Shoe Deal Finder"), DB filename still pre-brand — kept deliberately (E6). |
| **P2.3 price-history sparkline** (watchlist rows) | Was declared a cut-first stretch goal in Phase 2 | Unverified whether it shipped; treat as *probably not built*. Check `Deals.jsx` before planning. |

---

## 5. Features Planned

From the Phase-5 backlog and standing wishlist (roadmap.md — prompt 3 — will structure these properly):

- **Deal Alert Agent** and **Weekly Rotation Summary Agent** — the last Phase-5 backlog items; their natural surfaces (Home modules, Training tab) now exist by design.
- **Security pass** — API auth, rate limiting, MCP endpoint auth; the acknowledged precondition for everything below.
- **Native mobile client** — mobile-first constraints and API-first discipline already embedded for this.
- **Scheduled scraping** — implied by the unused APScheduler dependency; needs a real design (persisted job state) first.
- **Scraper coverage**: Sport Experts (custom FGL platform, "future"); Sporting Life only via paid unblocking (declined on principle — likely permanent no).
- Explored & deferred: remote MCP transport for ChatGPT; Email MCP; Coupon Hunting Agent.
- Server-side chat/conversation persistence (currently localStorage — design_decisions.md C8, scheduled to change).

---

## 6. Known Bugs & Quirks

No open *defect* list exists — bugs get fixed in-session and logged in `docs/changelog.md`. Standing known quirks (working-as-designed-but-sharp):

1. **MCP `trigger_scrape` full-catalog reliably times out client-side** (20–30 min job vs client timeouts). Workaround: per-shoe scrapes or the web UI. Documented, not fixed.
2. **`ShoeRun` proxy hazards (since the 2026-07-04 migration):** proxied fields (`distance_km`, `avg_pace`, …) do a lazy `Activity` load per row (N+1 in un-eager-loaded loops) and **silently don't work in SQLAlchemy `filter()`** — query against `Activity` columns instead. All existing code was migrated correctly; *new* code is where this will bite.
3. **Le Coureur titles sometimes remain French** despite the `/en` locale — cosmetic, known.
4. **Two retailers permanently dark** (Sporting Life: Cloudflare; Sport Experts: unbuilt custom platform) — the deal feed silently excludes them.
5. **Checkpoint "already prompted" state is per-browser** (localStorage) — a second device will re-prompt at the same checkpoint.
6. The three legacy `GET /api/scrape/test/*` endpoints predate the universal `POST /shoes/test` and are candidates for removal, not repair.

---

## 7. Technical Debt

Full ranked treatment: `refactoring/tech_debt.md` — **the ranked authority** (P0–P3 with states); actionable detail in `refactoring/refactor.md`; deletions in `refactoring/dead_code.md`. The short list a new session must know:

- **No auth on three mutation surfaces** + default `0.0.0.0` bind (deliberate; gates all exposure).
- **Dual schema authority** (`create_all` + Alembic) and DB + dated `.bak` files in the working tree.
- **`scraper_manager` compat shim** still fronting the decomposed scraper modules (4 call sites).
- **"Task D" leftover**: `coros_sync` router imports a private helper from `owned_shoes` router.
- **Fat legacy routers** (`watchlist`, `deals`, `dashboard`) with inline ORM logic — also what blocks MCP watchlist parity.
- **Whole-table in-Python reads** (`unified_activities`, watchlist reduction) — fine at 933 activities; the canonical table now makes indexed queries possible.
- Chat model catalogs hard-coded in the router vs prefix routing in the service; agentic loop implemented 3× (per provider).
- ~~**`claude.md`'s bottom overview sections are stale**~~ Fixed 2026-07-06: the changelog's stale tail was pruned (Retailer Status table relocated to `architecture.md` §10); the `docs/` suite is the reference material.
- APScheduler installed, unwired.

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
- **Unverified from this audit:** working-tree cleanliness. The `docs/` files generated by the documentation program (and this file) are likely **uncommitted** — commit them as a docs batch. The `.bak*` DB files' git status should be checked against `.gitignore` while you're there.
- The live SQLite DB sits in the tree; treat `main` + the DB file as jointly constituting "production."

---

## 11. Areas Requiring Immediate Attention

Ordered; "immediate" means *next few sessions*, not emergencies — nothing is on fire.

1. **Commit the documentation suite** — the program is complete (all prompts + final review + reconciliation); uncommitted, it's one `git clean` from gone. One batch: `docs/`, `refactoring/`, `CLAUDE.md`, `documentation_creation.md`, the rename. (R1.1)
2. **Guard the N+1/filter trap** while it's fresh: add eager-loading at the run-list seams and a short comment on `ShoeRun` warning against `filter()` on proxies — the one place the Phase-5 migration left future code exposed. (R1.4)
3. **Wire the Replacement Deals card on `/shoes/:id`** — a placeholder whose data dependency shipped; likely small, closes a visible loose end. (R1.3)
4. **Decide APScheduler** (design deliberately or remove) before any drive-by wiring collides with the single-process scrape lock. (R1.6)
5. **The security pass** stays the standing gate: schedule it before the agents if those agents will ever run unattended or the MCP port ever leaves the machine. (R2.1)
6. **Follow the review backlog**: `docs/documentation_review.md` §8 + addendum — next up after the commit: the INVARIANTS section in `CLAUDE.md`, then the skills implementation (S13 + S01 first).

---

*Maintenance note: this file describes 2026-07-06 and decays fastest of all the docs. Update the Snapshot date, §2 table, §9, and §11 at session end; move shipped items from §4/§5 into §3. When in doubt, the `docs/changelog.md` top entries are the source of truth for what happened; this file is the source of truth for what it means.*
