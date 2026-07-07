# Anton — Dependency Graph

**Companion to:** `docs/architecture.md`
**Generated:** 2026-07-04, from a full import audit of the repository.
**Revision note:** This document reflects the tree *after* the §3 Phase-5 canonical-activities migration (landed 2026-07-04: `Activity` model added, `ShoeRun` reduced to an attribution row, `StravaActivity` model and `strava_backfill.py` removed, migration `c3d4e5f6a7b8_canonical_activities`).

Legend: `→` = static Python import · `⇢` = runtime/network or data dependency (invisible to import analysis) · `⚠` = flagged in §7–§10.

---

## 1. Layer Map (Entry Points → External APIs)

The nominal layering, with what actually occupies each layer in this codebase:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ APPLICATION ENTRY POINTS                                                     │
│   run.py (uvicorn) · Vite SPA (HTTP) · Claude Desktop (MCP over HTTP)        │
│   CLI: app/scripts/{import_strava, seed_gear_mappings} · seed_data.py        │
│   alembic/env.py · pytest (tests/conftest.py)                                │
└───────────────┬─────────────────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ API LAYER (adapters)                                                         │
│   app/main.py — assembly, CORS, lifespan                                     │
│   app/routers/* — 17 REST routers                                            │
│   app/mcp_server.py — MCP tools/resources/prompts (a peer API surface)       │
│   app/routers/chat.py + services/chat_service.py — SSE/LLM gateway           │
└───────────────┬─────────────────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ SERVICES (domain logic)                                                      │
│   rotation · activities · strava_stats · strava_import · strava_gear         │
│   coros · home · races · settings                                            │
│   scrapers/orchestrator (scrape domain logic lives here, not in services/)   │
└───────────────┬─────────────────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ "REPOSITORIES" — ⚠ no formal repository layer exists                         │
│   The de-facto data-access layer is SQLAlchemy Session + models, used        │
│   directly by services AND (frequently) by routers/MCP tools.                │
│   The one true repository object: scrapers/deal_store.py (DealStore).        │
│   Thin honorary members: services/settings.py, scrapers/registry.py.         │
└───────────────┬─────────────────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ DATABASE                                                                     │
│   app/database.py (engine, SessionLocal, get_db, init_db)                    │
│   app/models/models.py (12 ORM models) → SQLite shoe_deals.db               │
│   alembic/ (authoritative migration list: architecture.md §5)                 │
└───────────────┬─────────────────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ EXTERNAL APIS                                                                │
│   8 retailer storefronts (Algolia ×2 · Shopify ×5 · headless Astro ×1)       │
│   COROS Open API (open.coros.com) · Anthropic / OpenAI / Google LLM APIs     │
│   ⇢ loopback: chat_service → this same app's /mcp endpoint                   │
│   ⇢ offline: Strava bulk-export CSV (file input, no live API)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

The honest summary of the layering: **Entry → API → (Service | ORM) → SQLite**. Services are the intended middle layer and the newer surfaces respect it strictly; a substantial minority of API-layer code reaches the ORM directly (§10).

---

## 2. Entry-Point Fan-Out

```
run.py ──uvicorn──▶ app.main
app.main → app.database (init_db)
         → app.mcp_server (mcp instance; mounted at /mcp, lifespan merged)
         → app.routers.{shoes, retailers, deals, dashboard, scraping, export,
                         coros_sync, owned_shoes, chat, admin, training, strava,
                         watchlist, activities, races, home}

alembic/env.py → app.database (Base, DATABASE_URL) → app.models.models   ⚠ schema authority
                                                                            shared with init_db
scripts/import_strava     → app.database (SessionLocal) → services.strava_import
scripts/seed_gear_mappings→ (database + services.strava_gear + models)*
seed_data.py              → (database + models)*
Vite SPA        ⇢ HTTP /api/*        (frontend/src/services/api.js — path strings)
Claude Desktop  ⇢ HTTP /mcp          (mcp-remote)
```
\* inferred from role; import blocks not individually audited this pass.

Everything transitively imports `app.database` and `app.models.models`; those two modules are the correct, intended "everyone depends on them" roots. `app.main` importing `app.mcp_server` at module level means **the entire scraper subsystem loads at boot** (mcp_server → scraper_manager → registry → all 8 bespoke scrapers → Playwright import).

---

## 3. API Layer → Downstream (per module)

### REST routers

| Router | Services used | Direct ORM / other | Pattern |
|---|---|---|---|
| `home` | services.home | — | ✅ thin adapter |
| `activities` | services.activities | — | ✅ thin |
| `training` | services.strava_stats | — | ✅ thin |
| `races` | services.races | models (query-by-id only) | ✅ thin |
| `strava` | — | models.Activity (4 aggregate queries) | small read-only |
| `owned_shoes` | services.rotation | models (CRUD queries, Deal/Shoe for replacement-deals) | mixed; hosts `_attach_computed_fields` |
| `coros_sync` | services.coros, services.settings | coros_client; **routers.owned_shoes** ⚠ | mixed |
| `chat` | services.chat_service | **models.OwnedShoe direct query** ⚠ (resource picker) | gateway |
| `scraping` | — | scrape_runner, scrape_state, scrapers.scraper_manager (shim) ⚠; function-level scraper imports ⚠ | operations |
| `shoes` | — | models + **scrapers.scraper_manager** ⚠ (scrapability test); CRUD inline | fat-ish |
| `retailers` | — | models + **scrapers.platform_detection** ⚠; CRUD inline | fat-ish |
| `deals` | — | models (all queries inline) | legacy inline |
| `dashboard` | — | models (aggregates inline) | legacy inline |
| `watchlist` | — | models (~100 lines of reduction logic inline) ⚠ | fat router |
| `export` | — | models (seed-source generation inline) | utility |
| `admin` | — | models + **scrapers.base_scraper.BaseScraper** ⚠ (kids-shoe regex as cleanup rule) | one-off |

### MCP server (`mcp_server.py`) — one module, five downstream families
```
mcp_server → database.SessionLocal
           → models.models (Activity, Deal, OwnedShoe, PriceRecord, Retailer, Shoe, ShoeNote, ShoeRun)
           → scrapers.scraper_manager (shim ⚠) — trigger_scrape
           → services.{rotation, coros, settings, strava_stats, races}
           → coros_client (config check)
```
Deal/shoe/retailer/price-history tools query the ORM directly (no service exists for those reads); rotation/training/races tools go through services. The module also carries its own dict serializers (`_deal_to_dict`, `_owned_shoe_to_dict`, …) — a second serialization system parallel to `models/schemas.py` (§9).

### Chat gateway
```
routers.chat → services.chat_service ⇢ HTTP(MCP_SERVER_URL) ⇢ /mcp (this same process) ⚠ runtime loop
chat_service → anthropic | openai | google SDKs ⇢ LLM APIs
```
`chat_service` has **zero imports from the rest of the app** — its entire coupling to Anton is over the network. Clean at import time; hidden at runtime (§8).

---

## 4. Services → Downstream

```
rotation      → models (OwnedShoe, ShoeRun, ShoeNote, Activity, ⚠ Deal, PriceRecord, Shoe)
activities    → models (Activity, OwnedShoe, ShoeRun) · rotation (pace formatting)
strava_stats  → activities (incl. ⚠ private _effective_moving_s) · rotation
strava_import → models (Activity) · pandas
strava_gear   → (pure — no app imports; deliberately DB-agnostic)
coros         → coros_client · models (Activity) · rotation · settings
home          → models (Deal, Retailer) · activities · rotation · settings
races         → models (PlannedRace) · rotation (pace formatting)
settings      → models (AppSettings)
chat_service  → (network only — see above)
```

Service-internal dependency shape (arrows point at the dependency):

```
            strava_stats ──▶ activities ──▶ rotation ◀── races
                 home ──▶ activities            ▲  ▲
                 home ──────────────────────────┘  │
                 home ──▶ settings ◀── coros ──────┘
```
`rotation` is the hub every run-domain service leans on — appropriate, since it owns the write path — **but it also imports `Deal`/`PriceRecord`/`Shoe`**, making it the single module where the two business domains meet (`active_deal_counts_by_type`, `find_matched_image`). That concentration is deliberate ("the heuristic bridge") but it means the rotation service can never be extracted without dragging the deals schema along (§9).

---

## 5. Scraper Subsystem (internal graph)

```
routers.scraping / mcp_server / scrape_runner / routers.shoes
        │
        ▼
scraper_manager.py  ⚠ backward-compat SHIM — pure re-exports
        │
        ├─▶ orchestrator.ScrapeOrchestrator ──▶ deal_store.DealStore ──▶ models
        │           │                                (all Deal/PriceRecord/PromoCode writes)
        │           └─▶ registry.build_registry ──▶ models.Retailer
        │                    │
        │                    ├─▶ 8 bespoke subclasses ─┐
        │                    ├─▶ shopify_scraper ──────┼──▶ base_scraper ⇢ retailer sites,
        │                    └─▶ algolia_scraper ──────┘        Playwright, *.algolia.net
        ├─▶ lock.py (process-wide threading.Lock — shared by ALL entry points)
        └─▶ (registry.build_dynamic_scraper)

scrape_runner → database · models · scrape_state · scraper_manager(shim)
platform_detection → requests only (used by routers.retailers)
```

This is the cleanest internal decomposition in the codebase — one-directional, persistence isolated in `DealStore`, qualification logic isolated in the orchestrator. The only wart is that **every consumer still enters through the shim**, so the refactor's module boundaries are invisible at call sites.

---

## 6. Frontend Dependency Edges (contract level)

```
pages/* → hooks/useApi.js (React Query) → services/api.js ⇢ /api/* path strings ⚠
ChatPage/ChatDrawer → hooks/useChatStream.js ⇢ POST /api/chat/message (manual SSE parse)
ScrapeButton et al. ⇢ GET /api/scrape/stream (EventSource)
lib/conversations.js ⇢ localStorage (chat history lives client-side only)
lib/shoeTypes.js ⚠ duplicates the backend's shoe-type vocabulary as a second copy
vite.config.js ⇢ dev proxy /api → 127.0.0.1:8000
```
There is no shared API-contract artifact (no generated client, no shared types); the frontend↔backend contract exists only as matching string literals and response-shape knowledge on both sides.

---

## 7. Circular Imports

**Hard Python import cycles: none.** The import graph is a DAG. Verified pressure points:

1. **`routers.coros_sync → routers.owned_shoes`** — the only sibling-router import (it pulls the private `_attach_computed_fields`). Not circular today, but it is one refactor away: if `owned_shoes` ever needs anything from `coros_sync` (plausible — sync status on the shoe response), the cycle appears. This edge is also the last remnant of the refactor's unfinished "Task D" (the `CHECKPOINT_INTERVAL_KM` re-export in `owned_shoes.py` exists solely to serve it).
2. **`app.models/__init__` aggregates `models.py` + `schemas.py`** — safe because `schemas.py` imports nothing from `models.py`, but the package `__init__` is the sort of aggregation point where a future "schema needs an ORM enum" import would create `models ↔ schemas` circularity through the package.
3. **Runtime (not import) cycle — the loopback loop:** `chat_service` → HTTP → `/mcp` → `mcp_server` → services → DB, all inside the same process that is currently serving the chat request. The import graph is acyclic *because the cycle was pushed onto the network*. It works (async server, tools on threadpool), but it is a genuine self-dependency: the app cannot answer a chat message unless it can reach itself over TCP at `MCP_SERVER_URL`.
4. **Protocol-level cycle:** `draft_shoe_review` uses MCP sampling — server asks the connected client's LLM for a completion, which the client could route back into tool calls. Bounded by the client, not by Anton.

---

## 8. Hidden Dependencies

Dependencies that don't appear in any `import` statement:

1. **`MCP_SERVER_URL` self-address** (`chat_service.MCP_SERVERS`). The assistant's entire toolset depends on this env var pointing back at the running process. Change the port, bind loopback-only differently, or run behind a proxy, and chat silently degrades to "No tools available." Nothing in the code marks this as self-referential.
2. **`ShoeRun` property proxies** (post-Phase-5). `distance_km`, `run_date`, `source`, `avg_pace`, `avg_hr`, `notes`, `coros_activity_id` on `ShoeRun` are now Python properties reading `self.activity`. Consequences invisible at call sites: (a) every "column" read is a lazy relationship load — any loop over `ShoeRun` rows that touches these is an **N+1 query pattern** unless the activity is eager-loaded; (b) these attributes can no longer be used in SQLAlchemy `filter()` expressions — code that compiles today (attribute access) and code that breaks today (query filters) look identical in grep. `coros.py` was correctly migrated to query `Activity`; the proxies exist so *readers* (schemas, resources, routers) didn't have to be.
3. **Duplicated pace formatting in the ORM layer.** `ShoeRun.avg_pace` re-implements `rotation.seconds_to_pace` inline (models can't import services without inverting the layering). Two copies of the same formatting rule now exist; they can drift.
4. **Router-prefix ↔ frontend-string contract.** `api.js` and every router prefix must agree by hand; ditto SSE event schemas (`useChatStream`, scrape stream) which are duplicated as string literals on both sides.
5. **Model catalogs vs. provider routing.** `routers/chat.py` hard-codes model IDs; `chat_service._get_provider` routes by name *prefix* (`gpt-`, `gemini-`, else Anthropic). Two files encode one fact ("which models exist and who serves them") with no shared source.
6. **The `sync_coros_runs` MCP prompt depends on a third party's tool schema** — it instructs the client to call `querySportRecords` with specific parameters on the *external* COROS MCP connector. A rename on COROS's side breaks the workflow with no signal in this repo.
7. **Function-level imports in `routers/scraping.py`** (`the_last_hunt`, `altitude_sports`, `jd_sports`, `models.models.Shoe/Retailer` inside handlers) — real dependencies hidden from any top-of-file audit.
8. **Dual schema authority.** `init_db()` `create_all` and Alembic both claim the schema; `alembic/env.py` importing the models makes migrations correct, but nothing forces a model edit to produce a migration. The canonical-activities change did it right (revision `c3d4e5f6a7b8`); the mechanism doesn't require it.
9. **`strava_stats → activities._effective_moving_s`** — a private-by-convention function imported across module boundaries; renaming it "safely" inside `activities.py` breaks stats.
10. **Environment as wiring:** `DATABASE_URL`, `ALLOWED_ORIGINS`, COROS credentials (whose *absence* is a feature flag), three LLM keys (whose presence drives `/chat/providers` availability). Feature availability is an emergent property of `.env` contents.

---

## 9. Tight Coupling

1. **`rotation` as the cross-domain knot.** It is simultaneously the run-domain hub (correct) and the only deals-domain client inside services (imports `Deal`, `PriceRecord`, `Shoe`). Every future attempt to treat "training" and "deals" as separable modules hits this one file.
2. **`coros_sync` ↔ `owned_shoes`** — private-helper import between sibling routers; response-shaping logic (`_attach_computed_fields`) trapped inside a router that another router needs.
3. **`mcp_server.py` as a monolith adapter.** ~20 tools + 7 resources + 1 prompt + 2 formatting helpers + hand-rolled dict serializers in one module, importing models, scrapers, and five services. It also embeds *business rules* (the 600/700/800 km threshold messages, the review-prompt template) that exist nowhere else — the adapter owns logic, so REST clients can never see those thresholds.
4. **Two serialization systems for the same aggregates.** Pydantic response models (REST) and `_*_to_dict` functions (MCP) must be kept in agreement by hand; the owned-shoe shape exists in at least three renderings (schema, MCP dict, resource markdown/JSON).
5. **Everything → `scraper_manager` shim.** Four consumers (scraping router, shoes router, mcp_server, scrape_runner) are coupled to the pre-refactor façade, so the decomposed modules (orchestrator/lock/registry) can't evolve their interfaces independently.
6. **Provider triplication in `chat_service`.** Three ~100-line agentic loops (Anthropic/OpenAI/Gemini) implement the same contract with copy-adapted control flow; a change to the event protocol (e.g., a new SSE event type) must be made three times.
7. **Frontend type vocabulary copy** (`lib/shoeTypes.js`) coupled by value to the backend's `shoe_type` strings — which are themselves the load-bearing cross-domain join key.

---

## 10. Layer Violations

Measured against the Entry → API → Services → Repository → DB ideal the project itself is converging on:

| # | Violation | Where | Severity |
|---|---|---|---|
| 1 | **API → ORM directly** (skipping services; no repository exists) | `deals`, `dashboard`, `watchlist`, `export`, `shoes`, `retailers` routers; `chat.py` resource picker; MCP deal/shoe/retailer tools | Structural — this is the old pattern the newer endpoints (`home`, `activities`, `training`, `races`) already abandoned. `watchlist` is the largest single instance (~100 lines of domain reduction in a router). |
| 2 | **Router → Router** | `coros_sync → owned_shoes._attach_computed_fields` | The clearest single violation; also the known "Task D" leftover. |
| 3 | **API → scraper internals** | `shoes` router → `ScraperManager`; `retailers` router → `platform_detection`; `admin` router → `BaseScraper.is_kids_shoe` | Moderate — scraping has no service façade, so routers reach into the subsystem. `admin` using a scraper's regex as a data-cleanup rule couples data hygiene to scraping internals. |
| 4 | **Business logic in adapters** | `mcp_server`: mileage-threshold messaging, review-prompt construction; `coros_sync`: skip-on-error confirmation policy | Logic invisible to the other API surface. |
| 5 | **Presentation in the model layer** | `ShoeRun.avg_pace` property formats a display string inside the ORM class (with duplicated logic) | Small but new (Phase-5); the model layer now owns a formatting rule. |
| 6 | **Entry-point layer doing schema work** | `init_db()` `create_all` at app startup alongside Alembic | Known issue (architecture.md §15.4); listed here because it is precisely a layer-authority violation. |

Not counted as violations: services querying the ORM directly (that *is* the data-access convention here — there is no repository layer to bypass), and the scraping router's use of the scrape subsystem (that is its job).

---

## 11. Suggestions for Simplification

Directional, ordered by leverage-per-effort. Several are completions of moves the codebase has already started.

1. **Finish "Task D": give owned-shoe response shaping a home in the services layer.** Moving `_attach_computed_fields` (and the checkpoint-constant re-export) out of `routers/owned_shoes.py` deletes the only router→router edge, un-traps the logic `coros_sync` needs, and gives MCP's `_owned_shoe_to_dict` a shared source — collapsing three renderings of the owned-shoe aggregate toward one.
2. **Delete the `scraper_manager` shim.** Four call sites; the modules it fronts are stable. Removing it makes the real orchestrator/lock/registry boundaries visible everywhere and ends the "temporary" coupling its own docstring warns about.
3. **Extract a tiny pure `pace` module** (below both models and services — no app imports). `rotation.pace_to_seconds/seconds_to_pace`, the `ShoeRun.avg_pace` proxy, and `coros_client.seconds_to_pace` (a third copy) all converge on it. This resolves the model-layer duplication without inverting layers, and pace formatting becomes one fact.
4. **Adopt one import convention for models** — either the `app.models` package façade or `app.models.models`, not both within the same file (currently `shoes.py`, `owned_shoes.py`, and others mix them). While there, fix the package `__init__` to export the current model set (it still lacks `Activity`-era names like `PlannedRace`/`StravaGearMapping`), or drop the façade entirely and import from `models.models` uniformly — the façade only earns its keep if it's complete.
5. **Promote `watchlist` (and eventually `deals`/`dashboard`) logic into a service**, matching the pattern `home`/`activities` already established. This is less about purity and more about the MCP surface: today MCP cannot expose the watchlist because its logic lives in a router; a `services/watchlist.py` makes REST + MCP parity free — the same argument that motivated every other service extraction here.
6. **Move adapter-owned business rules down one layer.** The 600/700/800 km thresholds belong next to `RETIREMENT_THRESHOLD` in `rotation`; the review-prompt template could live with rotation/notes logic. MCP tools then match the thin-adapter standard the module's own docstring claims.
7. **Make the loopback dependency explicit or remove it.** Cheapest: derive `MCP_SERVER_URL` from the server's own host/port config and log the self-connection at startup so failure is diagnosable. Better long-term: an in-process MCP transport (or direct service invocation behind the same tool interface) so the assistant no longer requires the app to reach itself over TCP — this also removes the hidden ordering constraint between the MCP session manager lifespan and first chat request.
8. **Eager-load `ShoeRun.activity` at the query seams.** Any list-of-runs read path (`get_shoe_runs`, resources, lifetime stats already migrated) should treat the attribution→activity join as mandatory, or the Phase-5 property proxies quietly reintroduce per-row queries. A single query helper ("runs with activities for shoe X") in `rotation`/`activities` centralizes it. Longer-term, migrating readers to `UnifiedActivity` and shrinking the proxy surface removes the trap entirely.
9. **Single-source the chat model catalog.** One structure (id, label, provider) consumed by both `/chat/providers` and `_get_provider` turns two-files-must-agree into one list.
10. **Share the shoe-type vocabulary.** Serve it from the backend (a constants endpoint or embedded in an existing aggregate) and delete `lib/shoeTypes.js` as an independent copy — it is the join key for the whole cross-domain bridge and currently exists in three places (backend strings, frontend list, MCP tool docstrings).
11. **Lift function-level imports in `routers/scraping.py` to module top** — or retire the three per-retailer `/test/*` endpoints outright, since `POST /shoes/test` (scrapability dry-run) now covers their purpose across all retailers.

None of these change behavior; each removes an edge from the graphs above. Items 1–4 are individually small and together would eliminate every ⚠ in §3 except the fat-router pattern, which item 5 addresses on its own schedule.
