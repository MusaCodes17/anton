# CLAUDE.md — Anton Development Guide

**Audience:** Claude Code (and any AI coding session) working in this repository.
**Read with:** `docs/project_state.md` (what's true right now) and `docs/ai_context.md` (orientation, once it exists). Deep references: `docs/architecture.md`, `docs/domain_model.md`, `docs/design_decisions.md`, `docs/dependency_graph.md`.
**Session changelog lives at `docs/changelog.md`** (formerly this file) — append a session entry there at the top after every working session. This file is the *stable* guide; the changelog is the *running* history.

---

## 1. Project Overview

Anton (repo: `running-shoe-deals` — old name kept deliberately) is a **single-user personal running platform** for a competitive runner in Montreal:

- **Deal watching** — track shoe models across 8 Canadian retailers; scrape, qualify, and surface genuine price opportunities.
- **Rotation & training** — canonical history of every run (`activities` table: Strava archive + COROS sync + manual), attribution of runs to owned shoes, wear/retirement lifecycle, training analytics, planned races.
- **AI surfaces** — an MCP server at `/mcp` (tools/resources/prompts/sampling) consumed by Claude Desktop, and an embedded assistant (**Son of Anton**) that is an MCP *client* of that same server.

Stack: FastAPI + SQLAlchemy 2 + SQLite + Alembic; React 18 + Vite + Tailwind + React Query (JSX, no TypeScript); `mcp[cli]` FastMCP. One process, one user, local-first, **no auth by explicit deferral** — never widen exposure casually.

The two business domains are **deliberately independent** (no FK between `shoes` and `owned_shoes`; they meet only through the `shoe_type` string heuristic). Do not "fix" this. See `docs/domain_model.md` §5.1.

---

## 2. Coding Philosophy

1. **Correct numbers, once.** Every derived value is computed server-side in exactly one place and served to all clients. If two surfaces could disagree about a number, the design is wrong.
2. **One sanctioned write path per invariant.** Run records go through `rotation.log_run()`. Deal-domain writes go through `DealStore`. Never add a parallel path; add parameters to the sanctioned one.
3. **Decisions are written down.** Non-obvious choices get a comment saying *why*; session results go in the changelog; reversible-decision candidates go in `docs/design_decisions.md`. Code that surprises without explaining is a defect here even when it works.
4. **The human is the tiebreaker.** Automation prepares and proposes; the runner confirms. No externally-sourced or AI-initiated write bypasses confirmation.
5. **Personal scale is a feature.** Prefer the simple O(N) that's honest about itself over speculative infrastructure — but respect declared budgets and never make scale decisions silently (label them, as the code already does).
6. **History is sacred in the training domain, disposable in the deals domain.** Runs, notes, and the Strava archive are never destroyed by normal operations; watchlist data dies with the interest. Keep the asymmetry.

---

## 3. Folder Conventions

```
backend/app/
  main.py          app assembly only — routers, CORS, /mcp mount, lifespan
  database.py      engine/session/get_db/init_db — don't add logic here
  mcp_server.py    MCP tools/resources/prompts — THIN adapters, like routers
  models/models.py ORM (12 models)   models/schemas.py Pydantic
  routers/         one file per resource; thin; HTTP concerns only
  services/        business logic — the only home for domain rules
  scrapers/        base + platform bases + one file per bespoke retailer;
                   orchestrator/registry/deal_store/lock are the real modules
                   (scraper_manager.py is a legacy shim — don't extend it)
  scripts/         CLI wrappers around services (argparse + exit codes only)
backend/tests/     pytest; one module per feature area
backend/alembic/   migrations — every schema change gets one (see §9)
frontend/src/
  pages/           route components; page-local sub-components inline in the page file
  components/      shared components; ui/ = shadcn-style primitives; feature
                   subfolders (chat/, training/, layout/) for cohesive sets
  hooks/useApi.js  ALL React Query hooks, grouped per API family
  services/api.js  the single axios client, grouped per domain
  lib/             pure helpers (no React, no fetch)
docs/              the documentation suite + changelog.md
.claude/skills/    13 workflow skills (S01–S13) — implemented per docs/skills_library.md:
                   add-service-capability · add-api-endpoint · add-database-model ·
                   data-migration · add-retailer · add-mcp-tool · ai-agent ·
                   add-frontend-page · write-tests · refactor-service ·
                   background-job · debugging · session-wrapup
```

Placement rules: new business logic → `services/` (never a router, never an MCP tool, never a React component). New endpoint → thin function in the matching router. New scraper → subclass in its own file, registered in `registry.py`. New query hook → `useApi.js`, calling a function added to `api.js`. Root planning docs (`REDESIGN_PLAN.md` etc.) are citable references — code comments cite them as `§N` / `P3.4`.

---

## 4. Architecture Principles

1. **Thin adapters.** Routers and MCP tools translate transport ↔ service calls. If an adapter grows a loop with domain meaning, extract to a service. (Legacy fat routers — `watchlist`, `deals`, `dashboard` — are debt to migrate, not precedent to copy.)
2. **REST/MCP parity.** A new capability ships as: service function → REST endpoint → MCP tool over the *same* function. If MCP can't expose it, the logic is in the wrong layer.
3. **Aggregate-per-page endpoints.** Pages get one round trip (`/api/home`, `/api/watchlist`). Derived fields attach at the boundary (`_attach_computed_fields`, `attach_derived`) — never stored, never recomputed client-side.
4. **Seams over rewrites.** `activities.unified_activities()` is the model: a read seam whose internals were swapped (two-store union → canonical table) with zero caller changes. When you can't fix something now, build the seam and note the plan.
5. **Graceful degradation.** Missing credentials disable a feature (return "not configured", don't raise); failed enrichment falls back (resource preload → tools; image → heuristic → placeholder); an unsupported MCP client gets an actionable message.
6. **Single-process assumptions are real.** The scrape lock and SSE state are in-memory. Do not add workers, schedulers, or background daemons without reading `docs/design_decisions.md` D4/D5/E5 first.

---

## 5. Coding Standards

**Python**
- Python 3.11+, type hints on all service signatures (`Optional[...]`, `list[...]` both in use — match the file you're in). `from __future__ import annotations` in newer service modules.
- Dataclasses for service-layer value objects (`RunLogResult`, `PipelineEntry`, `UnifiedActivity`); Pydantic only at the API boundary.
- Module docstring states the module's *job and rationale*; function docstrings explain behavior, edge cases, and **who owns the commit** where relevant; `Raises:` documented when callers must handle.
- Keyword-only arguments (`*,`) for multi-param service functions.
- Constants at module top with a comment (`RETIREMENT_THRESHOLD = 0.75  # §4 attention threshold...`).
- Units live in names: `distance_km`, `moving_time_s`, `avg_pace_s_per_km`, `mileage_at_note`. `*_at` = timestamp, `*_date` = local calendar date. Never an unlabeled number.

**JavaScript/React**
- Functional components + hooks; JSX; no TypeScript (don't introduce it piecemeal).
- Server state via React Query only — no bespoke fetch-in-useEffect. Mutations invalidate or optimistically patch (`onMutate`) their query keys.
- Tailwind with **design tokens**: colors/spacing through `index.css` variables and the theme — no hard-coded hex in components. Reuse `components/ui/` primitives.
- No new heavy frontend dependencies; charts stay on recharts.
- Every UI change passes desktop **and** ~380 px mobile before it's done.

**Both:** small diffs, phase-prefixed conventional commits (`p5: canonical activities migration`), one commit per numbered task.

---

## 6. Preferred Patterns (copy these)

- **Service function shape:** `def thing(db: Session, id: int, *, option: bool = True) -> Result:` — session first, keyword options, dataclass or ORM return, docstring with commit ownership.
- **Escape hatches over parallel paths:** `log_run(..., increment_mileage=False, commit=False)` lets batch callers reuse the invariant-preserving path. Extend this way.
- **Shared computation, thin projections:** `home._shoe_alerts` is a projection over `rotation.retirement_pipeline` — when two surfaces need the same answer, one computes, the other projects.
- **Idempotency by external ID:** unique `strava_activity_id`; dedup on `coros_activity_id` + date/distance fallback; re-running an import updates in place. Any new ingestion follows suit.
- **MCP write-tool envelope:** return `{"success": bool, ...}` dicts; read tools return plain data; resources return markdown *with* an embedded JSON block.
- **Confirmation protocol for synced/AI writes:** fetch → dedup → suggest (with stated heuristic) → **wait** → write via the sanctioned path → summarize → threshold check. (`sync_coros_runs` is the reference.)
- **Frontend data flow:** `api.js` function → `useApi.js` hook → page. Deep links carry state (`/deals?deal=id`), not globals.

**Known traps (do not rediscover these):**
- `ShoeRun`'s run fields (`distance_km`, `avg_pace`, …) are **property proxies** onto the joined `Activity`: they trigger lazy loads (N+1 in loops — eager-load the `activity` relationship at list seams) and they **silently do not work in `.filter()`** — query `Activity` columns instead.
- Pace: persisted as int seconds/km; `"M:SS/km"` strings are presentation only (`rotation.pace_to_seconds`/`seconds_to_pace`).
- "Shoe" is ambiguous: `Shoe` = watchlist entry, `OwnedShoe` = physical pair. Name variables accordingly.
- Timezone: run dates are **America/Toronto local dates**; converting from UTC first is mandatory.
- The Starlette/FastAPI/sse-starlette pins resolve an `mcp[cli]` conflict — don't bump them independently.
- `MCP_SERVER_URL` points the chat service back at *this same app*; changing bind/port affects Son of Anton. Since R2.1 the loopback must also send `Authorization: Bearer <ANTON_SECRET>` (injected by `chat_service._server_headers`) — drop it and the assistant *silently* loses all tools with no error.
- `strava_stats` imports the private-by-convention `activities._effective_moving_s` — renaming it "safely" inside `activities.py` breaks stats with no import-level signal.
- Router prefixes ↔ `api.js` paths (and the SSE event names on both sides of `useChatStream` / the scrape stream) are hand-matched string contracts — change one side, grep for the other.

---

## 7. Error Handling

- **Services raise, adapters translate.** Services raise `LookupError` (missing entity), `ValueError` (bad input/state), or let `requests.RequestException` propagate. Routers map: `LookupError → 404`, `ValueError → 400/502` (502 for upstream), `RequestException → 502`, scrape-in-progress → `409`. MCP tools catch and return `{"success": False, "error": "..."}` — tools never raise raw to the client.
- **Absence ≠ error:** unconfigured COROS returns `coros_configured=False` with empty results; empty pipelines/feeds return empty lists. Reserve errors for *broken*, not *missing*.
- **Idempotent no-ops are silent successes:** confirming an already-logged run returns `None`/skips — not an error.
- **Batch loops skip-and-continue with intent:** per-item failures in confirmations/scrapes are isolated (one retailer's failure never aborts the others) and surfaced in the summary, not swallowed.
- **Protective interlocks over cleverness:** the orphan-retirement "non-empty search" guard is the model — when a bulk operation could destroy data on a transient failure, require positive evidence first.
- Frontend: axios interceptor normalizes FastAPI error shapes; user-facing failures get a toast/inline state, never a blank crash; destructive actions get a confirmation dialog.

---

## 8. Logging Expectations

- Python `logging` with module loggers (`logger = logging.getLogger(__name__)`) in scrapers and services; log per-retailer/per-item outcomes at INFO, degradations at WARNING, isolated failures at ERROR *with context* (retailer, shoe, URL).
- MCP tools additionally use `ctx.log` for advisory notifications that should reach the LLM client (scrape completion, mileage thresholds).
- Startup prints (`✅ Database initialized`) are fine at boot; don't `print` inside request paths.
- Long-running jobs publish progress events (`scrape_state`) — user-visible progress is part of the feature, not optional telemetry.
- No secrets in logs, ever (API keys, COROS credentials).

---

## 9. Database Conventions

- **Every schema change = an Alembic migration** (batch mode / `render_as_batch=True` for SQLite). `init_db()`'s `create_all` exists for fresh setups only — never rely on it to apply a change to the live DB. (Resolving this dual-track is planned; until then, the migration is the source of truth.)
- **Structural/data-moving migrations follow the `canonical_activities` bar** (`docs/design_decisions.md` E4): reversible `downgrade`, explicit pre-migration backup (`shoe_deals.db.bak-<name>`), pre/post reconciliation of counts/totals against the live DB, suite green, UI spot-check — all recorded in the changelog entry.
- Tables: plural snake_case. Enums: lowercase strings from small closed sets (`active|retired|for_sale`). External IDs: `<system>_activity_id`, unique when they're the idempotency key. Server-side stamps (`mileage_at_note`, `created_at server_default=func.now()`) — never client-supplied.
- **Derived values are not stored** (cost/km, countdowns, pipeline %). The two blessed exceptions: the `current_mileage` ledger (single-write-path maintained) and a deal's qualifying-savings snapshot (MSRP-based since B9-v2; the deal's `target_price` column is a nullable reference only).
- Deletes are rare and rule-bound: price history is append-only; `source='strava'` activities survive attribution deletion; retirement is a status, not a delete.
- Sessions: `Depends(get_db)` in routers; `get_session()` context manager in MCP tools; one session per scraper worker thread. Don't share sessions across threads.
- Model relationship changes: check both `back_populates` sides and cascade intent; `activities ↔ shoe_runs` is `uselist=False` + unique FK on purpose.

---

## 10. Testing Expectations

- pytest in `backend/tests/`, one module per feature area, mirroring `test_home.py` / `test_rotation_overview.py` style: **test the rules, not the plumbing** — boundary cases named explicitly (exactly 75% is *in* the pipeline; empty week reads 0; case-insensitive type matching; race-today = 0 days).
- **Backend endpoints land with their tests before the consuming UI task starts** (REDESIGN_PLAN §5 — standing rule).
- Invariants deserve tests when touched: mileage ledger arithmetic (log + delete round-trip), dedup idempotency, checkpoint crossings, deal qualification/retirement.
- The full suite must be green at session end — 64 passing as of 2026-07-06 (the live count is authoritative in `docs/changelog.md`'s newest entry and `project_state.md` §2); a session that lowers that number isn't done. Removed features take their tests with them (as `strava_backfill` did).
- No frontend test harness exists; the frontend bar is: `vite build` clean, **0 console errors**, desktop + ~380 px visual pass. State the pass in the changelog entry.
- Scrapers: use the no-DB smoke endpoints / `POST /shoes/test` dry-run for live verification; don't build brittle HTML-fixture tests for retailer DOMs.

---

## 11. Refactoring Philosophy

- **One phase per session; one commit per numbered task.** Plan in a root doc with §-numbered items first if the work spans sessions; cite those §s from code comments.
- **Seam first, swap later:** isolate the read/write path behind one function, migrate callers to it, then change the internals invisibly (the `activities` seam is the proof).
- **Compatibility shims are allowed with an expiry:** proxies/re-exports that keep consumers stable during a restructure are good engineering (`ShoeRun` proxies, `scraper_manager`) — but they go on the debt list (`docs/design_decisions.md` verdict ⚠️) and get a removal sweep, not immortality.
- **Never refactor storage and behavior in the same change.** Phase 5 restructured storage under a "response shapes identical, counters untouched" contract — preserve observable behavior, prove it (reconciliation), then evolve behavior separately.
- Don't drive-by-fix debt outside the session's phase; note it in the changelog/backlog instead. Exception: correctness bugs.
- When reversing a documented decision, update `docs/design_decisions.md` (move to Superseded, name the successor) in the same session.

---

## 12. Performance Expectations

- **Budgets that exist:** `GET /api/home` < 200 ms locally (it's the future mobile launch screen). Scrape-all is expected to take 20–30+ min — that's politeness, not slowness; never "optimize" it by removing sleeps.
- In-Python whole-table passes are **acceptable and labeled** at current scale (~933 activities); if you add one, say so in a comment like the existing ones. The sanctioned path off them is indexed queries against `activities` — take it when a budget is threatened, not before.
- Watch the real hazards: N+1 via `ShoeRun` proxies (eager-load at list seams); per-request MCP reconnect in chat (known cost); Playwright startup in scrapers (reuse sessions per scraper instance, as `BaseScraper` does).
- Frontend: React Query caching is the performance strategy — correct query keys and invalidations matter more than memoization. Aggregate endpoints exist so pages make one round trip; don't fan out.
- No premature infrastructure: no caching layers, no task queues, no worker pools without a named budget being missed and a design-decision entry.

---

## 13. Documentation Standards

- **Every session ends with a changelog entry** at the top of `docs/changelog.md`: dated title, `[ADDED]/[CHANGED]/[REMOVED]/[BLOCKED]` tags, what/why/how-verified (test counts, visual passes, reconciliations). Write it like the existing entries — they are the project's memory.
- **Comment the whys:** thresholds cite their rationale, heuristics say "heuristic," pins carry their reason, scale compromises are labeled. A future session should never have to guess *why* — only *what next*.
- Keep the `docs/` suite truthful: structural changes update `architecture.md`/`domain_model.md`/`dependency_graph.md` sections they invalidate (each file's maintenance note says when); decisions worth reversing go in `design_decisions.md`; `project_state.md` gets refreshed at session end (it decays fastest).
- Docstrings on every service function and every model class; model docstrings explain the *domain meaning*, not the columns.
- New MCP tools: the docstring **is** the LLM-facing contract — write it for a model deciding whether/how to call it (args, semantics, side effects, confirmation requirements).
- Planning docs at root are append-only history once a phase ships — don't rewrite them to match reality; the changelog records what actually happened.

---

## Session Checklist (end of every working session)

1. Full pytest suite green; note the count.
2. `vite build` clean; 0 console errors; desktop + ~380 px pass for any UI change.
3. Migration written for any schema change (reversible + backed up if it moves data).
4. Changelog entry at top of `docs/changelog.md`.
5. `docs/project_state.md` refreshed (§2 status table, §9 recent decisions, §11 priorities).
6. Any reversed/new architectural decision recorded in `docs/design_decisions.md`.
7. Commits: one per numbered task, phase-prefixed.

---

## 14. Invariants

The checkable list. One line per invariant: what must hold → owning code path → covering test. The narrative behind each is `docs/domain_model.md` §4; this list is the canonical "never break these" reference (`docs/ai_context.md` §8 cites it; CLAUDE.md §6 remains the separate *mechanical traps* list). Verify the relevant lines whenever a session touches their paths.

- **INV-1 · Mileage ledger:** `current_mileage = starting_mileage + Σ attributed distances` — maintained, never recomputed → `rotation.log_run` / `rotation.delete_run` / `rotation.adjust_mileage` (the sole sanctioned manual override, journals the drift) → `tests/test_rotation.py` (increment) + `tests/test_activities_model.py` (delete round-trip) + `tests/test_owned_shoes.py` (PUT drops `current_mileage`/`starting_mileage`; `adjust_mileage` sets + notes). **C1 fixed 2026-07-07** — `PUT /owned-shoes/{id}` can no longer write the ledger; corrections go through `POST /owned-shoes/{id}/adjust-mileage`.
- **INV-2 · Single run writer:** every Activity + Attribution pair is born via `rotation.log_run` (escape hatches, never parallel paths) → `rotation.py` → no direct test of the "no parallel path" rule is possible; **documentation-only** — enforcement is convention + review (see refactor.md C1 for the one known breach).
- **INV-3 · Attribution uniqueness:** at most one shoe per activity (`shoe_runs.activity_id` UNIQUE) → structural (DB constraint, migration `c3d4e5f6a7b8`) → exercised in `tests/test_activities_model.py`.
- **INV-4 · Strava archive preservation:** `delete_run` on a `source='strava'` activity removes the attribution only; the archive row survives → `rotation.delete_run` → `tests/test_activities_model.py::test_delete_run_keeps_strava_archive`.
- **INV-5 · Dedup — never count a run twice:** `strava_activity_id` UNIQUE; COROS keys on `coros_activity_id` with a date + distance-within-0.1 km fallback; re-confirm is a silent no-op → structural + `coros.confirm_run` / the Strava importer → `tests/test_strava_import.py` + `tests/test_activities_model.py::test_coros_dedup_on_activity_coros_id`.
- **INV-6 · Deal qualification (B9-v2):** a deal exists iff `price < msrp` and `msrp IS NOT NULL`; savings measured against MSRP → `scrapers/orchestrator.py` (via `DealStore`) → `tests/test_deals.py` (3 tests — limited: retirement/requalification, the orphan guard, and promo rules remain uncovered; refactor.md H1/H2).
- **INV-7 · Derived-never-stored:** cost/km, countdowns, retirement %, weekly volume are computed at read time, never persisted → convention across `services/`; blessed exceptions are the mileage ledger (INV-1) and the deal's qualifying-savings snapshot → no test — see `docs/design_decisions.md` B13.
- **INV-8 · Confirmation gate:** no externally-sourced or AI-initiated run is logged without explicit human confirmation; no confidence exception → convention encoded in the MCP protocol (`sync_coros_runs` prompt; design_decisions C9) → no automated test; enforcement is prompt-and-review.
