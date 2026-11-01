# AGENTS.md — Anton Development Guide

**Reference docs** (`docs/`): `project_state.md` (what's true now), `roadmap.md` (what's next), `architecture.md`, `domain_model.md`, `design_decisions.md`, `dependency_graph.md`, `changelog.md` (session history; append an entry at the top after every working session). This file is the *stable* guide; the changelog is the *running* history.

**Reading the docs — they are large (60–380 KB each); never read one in full:**
- `project_state.md`: read §2 and §11 only, and only when you need the current priority (`/project:status`, `/project:next`, planning). A scoped task doesn't need it.
- `changelog.md`: read the top ~60 lines for the newest entry (live suite count, last session). Grep for anything older.
- `roadmap.md`, `design_decisions.md`, `architecture.md`: grep for the §, ID (`R12`, `C9`, `E4`) or term you need and read that section.

---

## 1. Project Overview

Anton is a **single-user personal running platform**: **deal watching** (Canadian retailers; bespoke + Shopify/Algolia scrapers in `scrapers/registry.py`), **rotation & training** (canonical `activities` table from Strava archive + COROS sync + manual runs, attribution to owned shoes, wear/retirement, analytics), and **AI surfaces** (an MCP server at `/mcp`, plus the embedded assistant **Son of Anton**, an MCP *client* of that same server).

Stack: FastAPI + SQLAlchemy 2 + SQLite + Alembic; React 18 + Vite + Tailwind + React Query (JSX); `mcp[cli]` FastMCP. One process, one user, internet-facing behind default-deny auth (session cookie for the SPA, named bearer tokens, OAuth 2.1 for the claude.ai connector) with one deliberately public read path, `GET /api/public/deals` — never widen exposure casually.

The two business domains are **deliberately independent** (no FK between `shoes` and `owned_shoes`; they meet only via the `shoe_type` string heuristic). Do not "fix" this (`docs/domain_model.md` §5.1).

---

## 2. Coding Philosophy

1. **Correct numbers, once.** Every derived value is computed server-side in one place.
2. **One sanctioned write path per invariant.** Runs go through `rotation.log_run()`; deal-domain writes through `DealStore`. Add parameters, never a parallel path.
3. **Decisions are written down.** Non-obvious choices get a comment saying *why*; reversible ones go in `docs/design_decisions.md`.
4. **The human is the tiebreaker.** No externally-sourced or AI-initiated write bypasses confirmation.
5. **Personal scale is a feature.** Prefer the simple honest O(N); respect declared budgets and label scale decisions.
6. **History is sacred in the training domain, disposable in the deals domain.** Runs, notes and the Strava archive survive normal operations; watchlist data dies with the interest.

---

## 3. Folder Conventions

```
backend/app/
  main.py          app assembly only
  database.py      engine/session/get_db/init_db — no logic here
  mcp_server/      THIN adapters; _core (FastMCP instance, get_session), _shared,
                   one module per domain; __init__ re-exports all
  models/          models.py ORM; schemas/ Pydantic, one file per domain
  routers/         one file per resource; HTTP concerns only
  services/        the only home for domain rules
  scrapers/        platform bases + one file per bespoke retailer; orchestrator/registry/deal_store/lock
  scripts/         CLI wrappers around services
backend/alembic/   migrations — every schema change gets one (see §9)
frontend/src/
  pages/           route components; page-local sub-components inline
  components/      shared; ui/ = shadcn-style primitives
  hooks/useApi.js  ALL React Query hooks (other hooks/ files are browser-state hooks)
  services/api.js  the single axios client, grouped per domain
  lib/             pure helpers (no React, no fetch)
.claude/skills/    flat reference docs, NOT auto-loaded as skills — read the relevant
                   file before that kind of work (add-api-endpoint, add-mcp-tool, data-migration, …)
.claude/commands/  project commands (`/project:<name>`); create-pr is the PR path
.claude/hooks/     local verification hooks (R13, E26), wired in `.claude/settings.json`
```

**Run locally** (the setup):
- Backend: `cd backend && python -m venv venv && venv/bin/pip install -r requirements.txt`; copy `.env.example` → `.env` (`DATABASE_URL` points at `~/anton-data/shoe_deals.db`); `venv/bin/python run.py` serves `127.0.0.1:8000` and runs `alembic upgrade head` on boot. Tests: `venv/bin/python -m pytest -q`.
- Frontend: `cd frontend && npm ci && npm run dev` (port 5173, proxies `/api` to `127.0.0.1:8000`)
- Production: `docker-compose.yml` + `deploy/` (architecture.md §11); connector setup: `docs/CLAUDE_DESKTOP_SETUP.md`.

Placement: business logic → `services/` (never a router, MCP tool, or React component). Endpoint → thin function in the matching router. MCP tool → the matching `mcp_server/<domain>.py`. Scraper → subclass in its own file, registered in `registry.py`. Query hook → `useApi.js`, calling a function added to `api.js`. A multi-session plan doc or spike report sits in `docs/` while in flight; when it ships, move lasting findings into `design_decisions.md` (and docstrings) and **delete the file**. Old plan names cited in code comments (`REDESIGN_PLAN §5`) live at commit bce3c53 under `docs/archive/` and `docs/spikes/`.

---

## 4. Architecture Principles

1. **Thin adapters.** Routers and MCP tools only translate transport ↔ service calls (legacy fat routers `watchlist`, `deals`, `dashboard` are debt).
2. **REST/MCP parity.** Service function → REST endpoint → MCP tool over the *same* function.
3. **Aggregate-per-page endpoints.** One round trip per page (`/api/home`, `/api/watchlist`). Derived fields attach at the boundary (`_attach_computed_fields`, `attach_derived`), never recomputed client-side.
4. **Seams over rewrites.** `activities.unified_activities()` is the model: a read seam whose internals changed with zero caller changes.
5. **Graceful degradation.** Missing credentials disable a feature ("not configured", don't raise); failed enrichment falls back.
6. **Single-process assumptions are real.** The scrape lock, SSE state and the one APScheduler instance (`services/schedule.py`: nightly scrape + COROS poll) are in-process (INV-9). New periodic work is a job on that scheduler, never a second scheduler or daemon. Read `docs/design_decisions.md` D4/D5 and INV-9 before adding workers.

---

## 5. Coding Standards

**Python**
- Python 3.11+; type hints on service signatures.
- Dataclasses for service value objects; Pydantic only at the API boundary. Session first, then keyword-only args (`*,`) in service functions.
- Docstrings: module states *job and rationale*; functions state **who owns the commit** and `Raises:`.
- Units live in names: `distance_km`, `moving_time_s`, `avg_pace_s_per_km`. `*_at` = timestamp, `*_date` = local calendar date.

**JavaScript/React**
- Functional components + hooks; JSX; no TypeScript (don't introduce it piecemeal).
- Server state via React Query only; mutations invalidate or optimistically patch (`onMutate`) their query keys.
- Tailwind **design tokens** (`index.css`, theme), no hard-coded hex; reuse `components/ui/`.
- No new heavy dependencies; charts stay on recharts. Every UI change passes desktop **and** ~380 px mobile.

**Both:** small diffs; phase-prefixed commits (`r12: inbox batch resolve`), one per numbered task.

---

## 6. Preferred Patterns (copy these)

- **Escape hatches over parallel paths:** `log_run(..., increment_mileage=False, commit=False)`.
- **Shared computation, thin projections:** `home._shoe_alerts` projects `rotation.retirement_pipeline`.
- **Idempotency by external ID:** unique `strava_activity_id`; dedup on `coros_activity_id` + date/distance fallback; re-imports update in place. New ingestion follows suit.
- **MCP envelope:** write tools return `{"success": bool, ...}`; read tools plain data; resources markdown *with* an embedded JSON block.
- **Confirmation protocol for synced/AI writes:** fetch → dedup → suggest (stated heuristic) → **wait** → write via the sanctioned path → summarize → threshold check (`sync_coros_runs` is the reference).
- **Frontend data flow:** `api.js` → `useApi.js` hook → page. Deep links carry state (`/deals?deal=id`).

**Known traps (do not rediscover these):**
- `ShoeRun` is attribution only: run data lives on `shoe_run.activity`. Eager-load `ShoeRun.activity` at list seams; filter on `Activity` columns.
- Pace: persisted as int seconds/km; `"M:SS/km"` strings are presentation only (`rotation.pace_to_seconds`/`seconds_to_pace`).
- "Shoe" is ambiguous: `Shoe` = watchlist entry, `OwnedShoe` = physical pair. Name variables accordingly.
- Timezone: run dates are **America/Toronto local dates**; converting from UTC first is mandatory.
- The Starlette/FastAPI/sse-starlette pins resolve an `mcp[cli]` conflict — don't bump them independently.
- MCP tools open sessions via `app.mcp_server._core.get_session()`: tests must patch that — patching `app.mcp_server.get_session` silently does nothing. New tools are re-exported from `mcp_server/__init__.py`.
- Son of Anton connects to the MCP server **in-process** by default (`ANTON_MCP_TRANSPORT=memory`, design_decisions C14), so bind, port and `MCP_SERVER_URL` don't matter. Only `ANTON_MCP_TRANSPORT=http` uses the loopback: `MCP_SERVER_URL` must reach the app and requests must send the `loopback` bearer (`chat_service._server_headers`); dropping it *silently* strips every assistant tool.
- `strava_stats` imports the private-by-convention `activities._effective_moving_s` — renaming it inside `activities.py` breaks stats with no import-level signal.
- COROS tool results are **prose, not JSON**: `coros_mcp_client` parses them with anchored regexes pinned by fixture tests (`tests/fixtures/coros/`). A rewording raises a loud `CorosContractError`, never nulls — refresh fixtures from a live capture (`COROS_LIVE=1`, `scripts/spikes/`) rather than loosening the parser. `COROS_TOKEN_KEY` must be set in the production `.env`; changing it makes stored tokens unreadable (UI says "reconnect needed").
- Router prefixes ↔ `api.js` paths (and SSE event names on both sides of `useChatStream` / the scrape stream) are hand-matched string contracts — change one side, grep for the other.

---

## 7. Error Handling

- **Services raise, adapters translate.** Services raise `LookupError` (missing entity), `ValueError` (bad input/state), or let `requests.RequestException` propagate. Routers map: `LookupError → 404`, `ValueError → 400/502` (502 for upstream), `RequestException → 502`, scrape-in-progress → `409`. MCP tools catch and return `{"success": False, "error": "..."}` — never raise raw.
- **Absence ≠ error:** unconfigured COROS returns `coros_configured=False` with empty results. Idempotent no-ops are silent successes.
- **Batch loops skip-and-continue:** per-item failures are isolated and summarized.
- **Protective interlocks:** when a bulk operation could destroy data on a transient failure, require positive evidence first (the orphan-retirement "non-empty search" guard).
- Frontend: failures get a toast/inline state; destructive actions get a confirmation dialog.

---

## 8. Logging Expectations

- Module loggers: outcomes INFO, degradations WARNING, isolated failures ERROR *with context* (retailer, shoe, URL). No `print` in request paths.
- MCP tools use `ctx.log` for advisory notifications. Long-running jobs publish progress events (`scrape_state`).
- No secrets in logs.

---

## 9. Database Conventions

- **Every schema change = an Alembic migration** (`render_as_batch=True` for SQLite). `init_db()`'s `create_all` is for fresh setups only — never rely on it to change the live DB.
- **Structural/data-moving migrations follow the `canonical_activities` bar** (`docs/design_decisions.md` E4): reversible `downgrade`, backup first (`shoe_deals.db.bak-<name>`), pre/post reconciliation against the live DB, suite green, UI spot-check, all recorded in the changelog.
- Tables: plural snake_case. Enums: small closed sets of lowercase strings. External IDs: `<system>_activity_id`, unique when idempotency keys. Server-side stamps (`mileage_at_note`, `created_at`) are never client-supplied.
- **Derived values are not stored**, except: the `current_mileage` ledger, a deal's qualifying-savings snapshot (MSRP-based; `target_price` is a nullable reference only), and best efforts / per-km splits (`activity_best_efforts`, `activity_splits`; source files aren't in the DB).
- Deletes are rule-bound: price history is append-only; `source='strava'` activities survive attribution deletion; retirement is a status.
- Sessions: `Depends(get_db)` in routers; `get_session()` in MCP tools; one per scraper worker thread, never shared.
- Relationships: check both `back_populates` sides and cascades; `activities ↔ shoe_runs` is `uselist=False` + unique FK on purpose.

---

## 10. Testing Expectations

- pytest in `backend/tests/`, one module per feature area: **test the rules, not the plumbing**, naming boundary cases (exactly 75% is *in* the pipeline; empty week reads 0).
- **Backend endpoints land with their tests before the consuming UI task.**
- Suite green at session end. The live count is in the newest `docs/changelog.md` entry; a session that lowers it isn't done. Removed features take their tests with them (the Stop hook's count guard allows a drop only when a test module is deleted).
- **CI is the gate** (`.github/workflows/ci.yml`, E15): every PR and push to `main` runs the backend suite (Python 3.11, no `backend/.env`) and `vite build`; merge only with both green. Tests must not depend on a local `.env` or test order (import-time env is set in `tests/conftest.py`).
- Local verification hooks (`.claude/settings.json`, `.claude/hooks/`) run affected tests after edits, guard the live DB, migrations and dependency pins, and gate Stop/SubagentStop. They are a pre-CI convenience; CI remains the merge gate. `/hooks` shows them; `disableAllHooks` in `settings.local.json` turns them off for a one-off.
- No frontend test harness: the bar is `vite build` clean, **0 console errors**, desktop + ~380 px pass, stated in the changelog.
- Scrapers: verify live via the no-DB smoke endpoints / `POST /shoes/test` dry-run; no HTML-fixture tests.

---

## 11. Refactoring Philosophy

- **One phase per session; one commit per numbered task.** If work spans sessions, put a §-numbered plan doc in `docs/` first (lifecycle in §3) and cite its §s from code comments.
- **Compatibility shims are allowed with an expiry:** they go on the debt list (`docs/design_decisions.md` ⚠️) with a removal sweep.
- **Never refactor storage and behavior in the same change.** Preserve observable behavior, prove it by reconciliation, then evolve behavior separately.
- Don't drive-by-fix debt outside the phase; note it in the changelog. Exception: correctness bugs.
- Reversing a documented decision: in the same session, move it to Superseded in `docs/design_decisions.md` and name the successor.

---

## 12. Performance Expectations

- `GET /api/home` < 200 ms locally. Scrape-all takes 20–30+ min by design; never remove its sleeps.
- In-Python whole-table passes over `activities` are **acceptable and labeled** at personal scale; label new ones in a comment. The way off is indexed queries, when a budget is threatened.
- Hazards: N+1 when `ShoeRun.activity` isn't eager-loaded; Playwright startup (reuse sessions per scraper).
- Frontend: correct React Query keys beat memoization; don't fan out requests.
- No caching layers, task queues, or worker pools without a missed budget and a design-decision entry.

---

## 13. Documentation Standards

- **Every session ends with a changelog entry** at the top of `docs/changelog.md`: dated title, `[ADDED]/[CHANGED]/[REMOVED]/[BLOCKED]` tags, what/why/how-verified.
- **Comment the whys:** thresholds cite rationale; heuristics and scale compromises are labeled.
- Structural changes update the `architecture.md`/`domain_model.md`/`dependency_graph.md` sections they invalidate.
- Docstrings on every service function and model class.
- New MCP tools: the docstring **is** the LLM-facing contract — write it for a model deciding whether/how to call it (args, semantics, side effects, confirmation requirements).

---

## Session Checklist (end of every working session)

1. Full pytest suite green locally (the Stop hook runs only affected tests, so run it via `/project:wrapup` or by hand) **and** both CI checks green; note the count.
2. `vite build` clean; 0 console errors; desktop + ~380 px pass for UI changes.
3. Migration for any schema change (reversible + backed up if it moves data).
4. Changelog entry at top of `docs/changelog.md`.
5. `docs/project_state.md` refreshed (§2, §9, §11).
6. Reversed/new architectural decisions recorded in `docs/design_decisions.md`.
7. Commits: one per numbered task, phase-prefixed.

---

## 14. Invariants

Canonical "never break these" list: rule → owning code (§6 is the separate *mechanical traps* list). **Covering tests are mapped in `docs/domain_model.md` §4.13** — read that table before changing code on an invariant's path, and run those tests. "No test" means review is the only guard.

- **INV-1 · Mileage ledger:** `current_mileage = starting_mileage + Σ attributed distances`, maintained, never recomputed → only `rotation.log_run` / `delete_run` / `adjust_mileage` (sole manual override, via `POST .../adjust-mileage`) / `reassign_attribution`. `PUT /owned-shoes/{id}` can't write it; the COROS poller and inbox, the best-efforts scan and `exclude_from_analysis` never touch it.
- **INV-2 · Single run writer:** every Activity + Attribution pair is born via `rotation.log_run` (escape hatches, never parallel paths) → `rotation.py` → **no test**.
- **INV-3 · Attribution uniqueness:** one shoe per activity → `shoe_runs.activity_id` UNIQUE.
- **INV-4 · Strava archive preservation:** `delete_run` on a `source='strava'` activity removes only the attribution → `rotation.delete_run`.
- **INV-5 · Never count a run twice:** `strava_activity_id` UNIQUE; COROS on `coros_activity_id` + date/distance-within-0.1 km fallback; re-confirm is a silent no-op → `coros.confirm_run`, the Strava importer.
- **INV-6 · Deal qualification:** a deal exists iff `msrp IS NOT NULL` and price is ≥ `MIN_DEAL_DISCOUNT_PCT` (default 5%) below MSRP — a floor, not `price < msrp` → `scrapers/orchestrator.py` via `DealStore`.
- **INV-7 · Derived-never-stored:** computed at read time → `services/`; the only stored exceptions are the ledger, the deal savings snapshot, best efforts and splits → **no test**.
- **INV-8 · Confirmation gate:** no externally-sourced or AI-initiated run is logged without explicit human confirmation, no confidence exception → MCP protocol (`sync_coros_runs`, C9) → **no test**.
- **INV-9 · Single Uvicorn worker:** the scrape lock, rate limiter, scheduler (scrape + COROS poll), poll tick lock and COROS token-refresh lock are all in-process → `backend/Dockerfile` `--workers 1` + `docker-compose.yml` → **no test**; check on restart.
- **INV-10 · Public surface is a pinned allowlist:** unauthenticated paths are exactly `PUBLIC_PATHS`; `GET /api/public/deals` returns `PublicDeal`, built field by field with no personal fields → `middleware/auth.py`. A new public path means editing the pinned set in the test (E20).
