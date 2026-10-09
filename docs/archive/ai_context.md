# Anton — AI Context

**Read this first.** This is the orientation document for any AI assistant opening this repository — the index to the documentation suite, not a copy of it. Where detail lives elsewhere, this file gives one sentence and a citation; follow the citation before acting.
**Generated:** 2026-07-06 (deliverable of documentation prompt 10, `docs/archive/documentation_creation.md`). Reflects the tree as of the **MSRP-drives-deals** change (2026-07-06, migration `d4e5f6a7b8c9`, `models.py` at 18,858 bytes, suite at **64 passing**).
**Update cadence:** this file ages fastest of the stable docs — refresh it at the start of every roadmap R-phase (`docs/roadmap.md` R1–R5) and whenever an entry in "Never change casually" or "Current priorities" ships or changes.

---

## 0. Freshness check (do this before trusting anything below)

The repo moves between sessions. Before acting on any time-sensitive claim in this file or its companions:

1. `stat backend/app/models/models.py` — **19,246 bytes (since 2026-07-07, R1.4 — a comment, no schema change)**. A *different* size means schema work has landed since; read the changelog before proceeding. (This doc's prose below still reflects the 2026-07-06 schema; no table has changed since.)
2. Read the **top entry of `docs/changelog.md`** — the current top is *"R2.1 — the security pass — 2026-07-07"* (suite **88**). Anything newer than that is not reflected here.
3. `docs/project_state.md` carries its own snapshot date in its header; if it's older than the changelog's top entry, trust the changelog.

`refactoring/refactor.md` and `refactoring/tech_debt.md` carry the same protocol in their maintenance notes (re-stamped 2026-07-06 against the MSRP-drives-deals state — see their headers).

---

## 1. What Anton is

Anton (repo `anton` — renamed from `running-shoe-deals` on 2026-07-14; design_decisions E6) is a **single-user personal running platform** for a competitive marathon runner in Montreal. One FastAPI process + SQLite file + React SPA, all local, no auth (deliberate deferral — E1). Three concerns:

1. **Deal watching** — a size-less watchlist of shoe models scraped across 8 Canadian retailers; a deal is any price **below the shoe's MSRP** (design_decisions **B9-v2**, 2026-07-06), retired honestly when it stops qualifying or vanishes from search.
2. **Rotation & training** — a canonical history of every run (`activities` table: 8-year Strava archive + COROS sync + manual logs; 933 activities, ~8,028 km), attribution of runs to owned shoes, a mileage-ledger wear/retirement lifecycle, training analytics, planned races.
3. **AI surfaces** — a full MCP server at `/mcp` (tools/resources/prompts/sampling) consumed by Claude Desktop, and **Son of Anton**, an embedded multi-provider chat assistant that is an MCP *client* of that same server over loopback.

The app is in daily real use; the live DB in the tree is the only DB ("production"). The two business domains are **deliberately independent** — no FK between `shoes` (wanting) and `owned_shoes` (owning); they meet only through the `shoe_type` string heuristic (domain_model §5.1, §4.3).

## 2. Long-term vision

Anton is evolving from a finished redesign into a **long-term personal AI platform** (roadmap R1–R5): secured core (R2.1 security pass is the gate in front of everything), proactive agents under confirmation gates (R3: weekly rotation summary, deal alerts, race-block advisor), scheduled scraping with real observability (R4), and eventually a native mobile client, remote access, richer ingestion (FIT files, weather), and decade-scale longitudinal analytics (R5). The meta-bet (R5.6): sessions that start with accurate written context outperform sessions that start with archaeology — this documentation suite *is* infrastructure.

## 3. Project philosophy

The six principles in CLAUDE.md §2, compressed: **correct numbers, once** (every derived value computed server-side in exactly one place); **one sanctioned write path per invariant** (`rotation.log_run`, `DealStore`); **decisions are written down** (changelog, design_decisions, §-cited planning docs); **the human is the tiebreaker** (automation proposes, the runner disposes — no AI/synced write bypasses confirmation); **personal scale is a feature** (honest labeled O(N) over speculative infrastructure); **history is sacred in the training domain, disposable in the deals domain** (append-only notes and frozen archive vs. watchlist data that dies with the interest).

## 4. Folder structure

```
docs/                 the reference suite (this file, architecture, domain_model,
                      design_decisions, dependency_graph, roadmap, project_state,
                      skills_library, changelog — the session-by-session history)
refactoring/          refactor.md (code review) · tech_debt.md (ranked ledger) ·
                      dead_code.md (deletion inventory)
CLAUDE.md             the coding guide — conventions, patterns, traps, session checklist
docs/archive/         retired docs + completed execution plans (REDESIGN_PLAN, REFACTOR_PLAN,
                      TRAINING_DEPTH_PLAN, SECURITY_PASS_PLAN, documentation_creation, …) — moved
                      here H2 2026-07-14; append-only history, code cites them as §N/P3.4
backend/
  run.py              uvicorn entrypoint (binds 127.0.0.1:8000 by default since R2.1; API_HOST=0.0.0.0 opts into LAN — see E7)
  shoe_deals.db       the live DB (+ .bak* restore points, incl. .bak-msrp-drives-deals)
  alembic/            baseline + 5 migrations; latest d4e5f6a7b8c9_msrp_drives_deals
  tests/              pytest, 16 modules, 88 passing
  app/
    main.py           assembly only · database.py engine/session · mcp_server.py MCP adapters
    models/models.py  12 ORM models · models/schemas.py Pydantic
    routers/          17 thin(ish) REST routers · services/ ALL business logic
    scrapers/         registry → orchestrator → deal_store + lock; scraper_manager is a shim
    scripts/          CLI wrappers (import_strava, seed_gear_mappings)
frontend/src/
  pages/ components/  React 18 + Vite + Tailwind, JSX (no TS)
  hooks/useApi.js     all React Query hooks · services/api.js the single axios client
  lib/                pure helpers (incl. shoeTypes.js — a known duplicate of backend vocab)
```

Placement rules (CLAUDE.md §3): new business logic → `services/`, never a router/MCP tool/component; new endpoint → thin function in the matching router **plus** an MCP twin; new scraper → subclass + `registry.py`; new query hook → `useApi.js` over a function in `api.js`.

## 5. Architecture summary

Full reference: `docs/architecture.md` (§1 overview diagram, §4 request lifecycles, §5 schema, §9 AI layer, §10 scrapers); import-level companion: `docs/dependency_graph.md`.

- **One process, three surfaces:** `/api/*` REST (17 routers), `/api/chat/*` SSE (Son of Anton), `/mcp` (FastMCP, Streamable HTTP). All three sit over the same services layer and the same SQLite file.
- **Stack:** Python 3.11 / FastAPI 0.109 (pinned — see §8) / SQLAlchemy 2 / Alembic (batch mode) / `mcp[cli]` 1.28; React 18 / Vite / React Query / Tailwind, no TypeScript.
- **Layering:** Entry → API adapters → services → ORM → SQLite. The newer surfaces (`home`, `activities`, `training`, `races`, `rotation-overview`) are strictly thin; legacy routers (`watchlist`, `deals`, `dashboard`) still hold inline ORM logic — that is flagged debt (tech_debt P1-10), not precedent.
- **The canonical run store:** every physical run is one `activities` row (`source` = strava|coros|manual); `shoe_runs` is a pure attribution row with read-only property proxies preserving the old response shapes (architecture §5, design_decisions B4/B5). All reads converge on the `activities.unified_activities()` seam; all writes on `rotation.log_run()`.
- **Deal pipeline:** registry builds scrapers (2 Algolia, 5 Shopify, 1 bespoke) → orchestrator qualifies (`price < msrp`, B9-v2) → `DealStore` owns every write → process-wide lock serializes all scraping; background scrape-all streams SSE progress with replay.
- **AI layer:** ~20 MCP tools, 7 markdown+JSON resources, the `sync_coros_runs` agent prompt, and sampling (`draft_shoe_review`). Son of Anton discovers tools automatically by being an MCP client of `MCP_SERVER_URL` — which points back at **this same process** (dependency_graph §7.3/§8.1).
- **Self-referential quirks to know on day one:** the loopback above; the `ShoeRun` proxies (N+1 unless eager-loaded; silently broken in `.filter()` — use `Activity` columns); America/Toronto is the calendar for run dates; pace persists as int seconds/km.

## 6. Important design decisions

The historical record is `docs/design_decisions.md` (A=platform, B=domain, C=AI, D=scraping, E=process; each entry carries a verdict). The load-bearing ✅ Keeps: A1 local-first single-process · A4 API-first server-computed numbers · B1 no shoe↔owned-shoe FK · B4/B5 canonical activities + proxy bridge · B6/B7 mileage ledger + single write path · **B9-v2 MSRP-drives-deals (current; supersedes B9)** · B10 orphan-retirement non-empty guard · B11 frozen Strava archive · B13 derived-never-stored · B14 Toronto calendar · C1 MCP as the single AI substrate · C9 confirmation gates · D3 politeness/no-bot-bypass · D4 one scrape lock, refuse-don't-queue · E4 the migration-discipline bar.

The ⚠️ **scheduled-to-change set** (the standing to-do list of decided change): **A6** dual schema authority · **C8** chat history in localStorage. (Executed and now Superseded: **E1** no-auth → **E7** bearer token, 2026-07-07 R2.1; **D7** `scraper_manager` shim + **E5** APScheduler, 2026-07-07 R1.) The Superseded table at the bottom of design_decisions is required reading before "fixing" anything that looks odd — several oddities are the corpses of already-reversed decisions.

## 7. Coding conventions

`CLAUDE.md` is authoritative; it is short and should be read in full. The headline rules: services own logic with session-first keyword-only signatures and docstrings stating commit ownership (§5–6); routers/MCP tools are thin adapters that translate errors (`LookupError→404`, `ValueError→400/502`; MCP returns `{"success": False, ...}`, never raises) (§7); every schema change gets a reversible Alembic migration, with the E4 ceremony (backup + reconciliation) for anything that moves data (§9); tests test rules and boundaries, suite green at session end with the count recorded (§10, currently **64**); one phase per session, one commit per numbered task, phase-prefixed (`p5:`/`r1:`); **every session ends with a changelog entry** at the top of `docs/changelog.md` and a `project_state.md` refresh (§13 + Session Checklist). Units live in names (`distance_km`, `avg_pace_s_per_km`); frontend is React Query + design tokens only, verified at desktop and ~380 px. The known traps list (CLAUDE.md §6) is the cheapest bug prevention in the repo — read it.

## 8. Things that should never be changed casually

These are the load-bearing decisions and invariants a well-meaning session is most likely to accidentally violate. Each names its authority — read it before touching. **The canonical checkable form of the invariants below — one line each with owning code path and covering test — is `CLAUDE.md` §14 (INV-1…INV-8); this section cites it rather than restating the rules.** (`CLAUDE.md` §6 remains the separate mechanical-traps list.)

1. **`Shoe` ≠ `OwnedShoe`, and there is no FK between them.** Wanting and owning are independent facts; the *absence* of a relationship is the design. Do not "fix" it, do not model purchases as a transition. (design_decisions B1, domain_model §5.1)
2. **`rotation.log_run` is the only run writer.** Manual, COROS, and Strava ingestion all go through it; a second write path breaks the mileage-ledger identity. Extend it with keyword escape hatches, never parallel it. (Canonical: CLAUDE.md §14 **INV-2**, with the ledger identity itself as **INV-1**; narrative: domain_model §4.6, design_decisions B7 — and see tech_debt P0-1 for the one known breach)
3. **`source='strava'` activities are the frozen archive.** Deleting an attribution must never delete an archive activity; the 8-year history is re-curatable, never destructible. (Canonical: CLAUDE.md §14 **INV-4**; narrative: domain_model §4.8, design_decisions B11)
4. **Confirmation gates on all AI/synced writes.** No run is ever auto-logged; agents present suggestions (heuristic stated) and *wait*. There is no confidence exception. (Canonical: CLAUDE.md §14 **INV-8**; narrative: design_decisions C9, domain_model §5.3/§5.5)
5. **Derived values are never stored.** Cost/km, countdowns, retirement %, weekly volume — computed at read time. Blessed exceptions only: the mileage ledger (stored counter, B6) and a deal's qualifying-savings snapshot (now MSRP-based, B8/B9-v2). (Canonical: CLAUDE.md §14 **INV-7**; narrative: design_decisions B13)
6. **Deals qualify against MSRP, not target_price** (since 2026-07-06). `target_price` is an optional personal threshold with no role in qualification or savings; a shoe without MSRP produces no deals by design. Don't reintroduce target into deal math. (Canonical: CLAUDE.md §14 **INV-6**; narrative: design_decisions B9-v2; changelog 2026-07-06)
7. **The FastAPI/Starlette/sse-starlette pin triple** resolves an `mcp[cli]` version conflict. Never bump any of the three independently. (design_decisions A7, CLAUDE.md §6)
8. **`ShoeRun` proxies are read-only presentation.** They lazy-load (N+1 in loops — eager-load `activity` at list seams) and **silently do not work in `.filter()`** — query `Activity` columns. (dependency_graph §8.2, CLAUDE.md §6, refactor.md H4)
9. **The `shoe_type` string vocabulary is the cross-domain join key.** Backend-owned since R2.4 (`app/utils/shoe_types.py`, served at `GET /api/shoe-types`, validated on write — off-vocab is a 422; the frontend copy is deleted). Still treat vocabulary edits as schema-grade — both domains must agree on the exact strings. (domain_model §4.3/§7.1; the `shoe_type` half of tech_debt P1-5 is resolved — owned-shoe `status` validation, M2, remains.)
10. **Auth is a shared bearer token (R2.1 shipped 2026-07-07) — send it, don't widen exposure casually.** Every request to `/api/*` and `/mcp` needs `Authorization: Bearer <ANTON_SECRET>` (app-wide pure-ASGI middleware, `app/middleware/auth.py`); exempt: `/`, `/health`, `/api/health`, OPTIONS. Default bind is `127.0.0.1`; the app fails fast if `ANTON_SECRET` is unset. The SPA (`VITE_ANTON_SECRET`), Claude Desktop (`mcp-remote --header`), and the loopback client all send it. Any *further* reach increase (unattended agents, mobile, remote MCP) still gets weighed. (design_decisions **E7** ← E1; `docs/archive/SECURITY_PASS_PLAN.md`; `CLAUDE_DESKTOP_SETUP.md`; architecture §11)
11. **`MCP_SERVER_URL` is a self-reference.** It points back at this same process; changing bind/port silently degrades Son of Anton to "no tools." (dependency_graph §8.1)
12. **The scrape lock's posture is refuse, not queue** — and it assumes exactly one process/worker. Don't wire APScheduler or add workers without reading D4/D5/E5 and roadmap R4.1. (design_decisions D4)
13. **Migrations that move data follow the E4 bar** — reversible downgrade, named `.bak` backup, pre/post reconciliation recorded in the changelog. `c3d4e5f6a7b8` (canonical activities) and `d4e5f6a7b8c9` (MSRP) are the reference implementations. (design_decisions E4, CLAUDE.md §9)

## 9. Current priorities

(Aligned with `project_state.md` §11 as of 2026-07-06.)

1. **Documentation program: ✅ complete and committed** (2026-07-06, R1.1) — the full suite, `CLAUDE.md` (incl. the §14 INVARIANTS list), `refactoring/`, and the `.claude/skills/` library are in git. The review backlog (`docs/documentation_review.md` §8) is closed through step 4; the anti-drift process rules (step 5) are adopted going forward.
2. **Same-day-sized safety fixes from the review:** refactor.md **C1** (writable `current_mileage` — the one P0 invariant breach; make the UI's mileage-adjust an explicitly sanctioned `rotation.adjust_mileage()`) and **M3** (scrape-lock wedge). Note: refactor.md's own maintenance rule says re-verify C1/H3/H4 now that `models.py` changed size — the MSRP change touched schemas/orchestrator/deal_store, not the rotation paths, so the findings almost certainly stand, but check before acting.
3. **R1 loose ends** (roadmap R1, order 1→2→4→3→5→6): prune the changelog's stale bottom sections; guard the `ShoeRun` proxy traps (eager-loading — refactor.md H4); wire the Replacement Deals card on `/shoes/:id` (data shipped 2026-07-04); debt sweep #1 (Task D, shim deletion, pure `pace` module, model-catalog single-sourcing); decide APScheduler.
4. **Deal-domain tests beyond today's three:** `test_deals.py` now pins MSRP savings/refresh/no-MSRP — but retirement/requalification, the orphan guard (and its H2 partial-failure gap), and promo manual-beats-scraped remain untested (refactor.md H1/H2).
5. **The security pass (R2.1) shipped** (2026-07-07, Session D) — bearer token on `/api`+`/mcp`, loopback default bind, E1 → E7. The exposure gate is closed; **live go-live is a documented human step** (`CLAUDE_DESKTOP_SETUP.md`). Next in R2: rate limiting (`/api/chat/message`), then R2.2 schema authority.

## 10. Current roadmap

Full plan with rationale, dependencies, and complexity: `docs/roadmap.md`. The spine:

**R1 — loose ends** (docs committed, proxy guards, replacement-deals card, debt sweep, APScheduler decision) → **R2 — core platform** (2.1 security pass → 2.2 schema authority → 2.3 indexed reads over `activities` → 2.4 shoe-type vocabulary → 2.5 scrape observability → 2.6 server-side chat memory) → **R3 — AI capabilities** (weekly rotation summary agent first, then MCP watchlist parity, review pipeline, deal alerts, notification channel, race-block advisor) → **R4 — automation** (scheduled scraping, agent scheduling/delivery, COROS cadence nudges, coupon hunting, scraper watchdog) → **R5 — long-term** (mobile client, remote access, purchase-loop closure, richer ingestion, longitudinal analytics, documentation-as-infrastructure permanently).

Two rules fall out of the dependency spine: **nothing unattended before R2.1**, and **nothing scheduled before R2.5**.

## 11. Known technical debt

The ranked ledger is `refactoring/tech_debt.md` (P0–P3 with states); actionable detail in `refactoring/refactor.md`; deletions in `refactoring/dead_code.md`. The items a new session must hold in mind:

| Rank | Item | Detail |
|---|---|---|
| P0-1 | Writable mileage ledger via `PUT /owned-shoes/{id}` (blind setattr; UI uses it deliberately — an *undocumented invariant exception*) | refactor.md C1 |
| P0-2 | No auth ×3 mutation surfaces on a `0.0.0.0` default bind | refactor.md C2; E1 ⚠️ |
| P1-1 | `ShoeRun` proxy N+1 live in today's run-list endpoints + silent `.filter()` no-op | refactor.md H4 |
| P1-2 | Orphan retirement retires live deals on partial detail-fetch failure | refactor.md H2 |
| P1-3 | `DELETE /owned-shoes/{id}` bypasses rotation semantics; SQLite FK enforcement off process-wide | refactor.md H3 |
| P1-4 | Deal domain nearly untested (narrowed 2026-07-06: 3 MSRP tests exist; retirement/orphan/promo rules still uncovered) + zero HTTP-layer tests | refactor.md H1 |
| P1-5 | `shoe_type`/`status` vocabulary: 4 copies, no boundary validation | refactor.md M2 |
| P1-6/7 | `mcp_server.py` god object with embedded business rules; two serialization systems for the same aggregates | tech_debt §4.1/§5.1 |
| P1-8 | Provider agentic-loop ×3 + duplicated model catalogs — consolidate **before** the R3 agents extend it | tech_debt §5.2 |
| P1-9 | Dual schema authority (`create_all` + Alembic) — precondition for further structural migrations | A6 ⚠️ |
| P1-10 | Fat legacy routers (`watchlist`/`deals`/`dashboard`) blocking MCP watchlist parity | tech_debt §6.1 |

**Documentation staleness register (as of the 2026-07-06 docs-reconciliation session): clear.** The MSRP ripple (domain_model §4.1/§7.1, architecture §5/§6/§12, CLAUDE.md §9, refactor L2, tech_debt §9.5), the changelog's stale tail (pruned; Retailer Status table relocated to architecture §10), the `claude.md` ghost references, and the 61→64 count drift were all fixed — see the changelog entry of that date and `docs/documentation_review.md`. Add new entries here whenever a change lands without its documentation updates, and prune them when reconciled.

## 12. Recommended reading order

**For any session:** this file → `CLAUDE.md` → `docs/changelog.md` (top 2–3 entries) → `docs/project_state.md` (mind its snapshot date).
**For feature work:** + `domain_model.md` §4–§5 (the constitution and who owns what) → `architecture.md` §7–§8 (services and API patterns) → `roadmap.md` (is this already sequenced?).
**For schema/migration work:** + `design_decisions.md` B4/E4 (the worked example and the bar) → `dependency_graph.md` §3 → `CLAUDE.md` §9. Skills S03/S04 in `skills_library.md` outline the step-by-step.
**For AI/MCP work:** + `architecture.md` §9 → `design_decisions.md` C1–C9 (C9 is non-negotiable) → the `sync_coros_runs` prompt in `mcp_server.py` as the reference agent protocol.
**For scraper work:** + `architecture.md` §10 → `design_decisions.md` D1–D7 (D3: no bot-bypass, ever) → skills S05.
**For refactoring:** + `refactoring/refactor.md` (findings with solutions) → `dependency_graph.md` §§7–11 (the debt map and its sequencing) → `CLAUDE.md` §11 (seam-first philosophy).
**For debt triage:** + `refactoring/tech_debt.md` (the ranked ledger and what's decided vs. open) → `design_decisions.md` ⚠️ verdicts → `refactoring/dead_code.md` before deleting anything.

`docs/skills_library.md` designs 13 workflow skills (S01 add-service-capability through S13 session-wrapup) that trace curated paths through all of the above; **implemented 2026-07-06 in `.claude/skills/`** (index in CLAUDE.md §3). The library file remains the design authority; the skill files cite rather than restate.

---

*Maintenance note: this document is the suite's index and decays fastest after `project_state.md`. Refresh it at the start of every R-phase, when a "never change casually" entry gains or loses an item, when the freshness anchors in §0 move (models.py size, newest changelog entry, test count), and when the staleness register in §11 is reconciled. If this file and a companion disagree, the companion's own maintenance note decides which is stale — and the changelog's top entries are the final arbiter of what actually happened.*
