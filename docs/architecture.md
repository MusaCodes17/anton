# Anton — Architecture Reference

**Repository:** `running-shoe-deals`
**Document status:** Technical due-diligence audit. First written 2026-07-04; **refreshed 2026-07-04 after the §3 Phase-5 canonical-`activities` migration landed** (revision `c3d4e5f6a7b8`). This document describes the post-migration architecture.
**Companion:** `docs/dependency_graph.md` (full import-edge audit, coupling and layer-violation analysis).
**Scope:** Descriptive reference. No implementation changes are proposed here; the final section lists architectural directions only.
**Framing assumption:** Anton is a long-term personal platform (web + MCP + assistant today; mobile client anticipated), not a single-purpose app.

---

## 1. High-Level Architecture

Anton is a **single-user, locally-hosted personal platform** composed of one Python backend process and one React SPA, joined by three interface surfaces that all sit on the same FastAPI application:

```
                         ┌────────────────────────────────────────────────┐
                         │            FastAPI process (port 8000)         │
                         │                                                │
 React SPA (5173) ──────▶│  /api/*        REST routers (17 routers)       │
   (Vite dev proxy)      │  /api/chat/*   SSE chat (Son of Anton)         │
                         │  /mcp          MCP server (Streamable HTTP)    │
 Claude Desktop ────────▶│                                                │
   (via mcp-remote)      │  ┌──────────── Services layer ──────────────┐ │
                         │  │ rotation · activities · home · races      │ │
 Son of Anton ──┐        │  │ coros · strava_* · settings · chat        │ │
 (chat_service  │        │  └──────────────────┬────────────────────────┘ │
  is an MCP     └───────▶│                     │ SQLAlchemy ORM           │
  *client* of            │  ┌──────────────────▼────────────────────────┐ │
  its own /mcp           │  │ SQLite (shoe_deals.db)                    │ │
  over loopback)         │  └───────────────────────────────────────────┘ │
                         │                                                │
                         │  Scraper subsystem (registry → orchestrator   │
                         │  → deal store), sync + background/SSE modes   │
                         └───────┬───────────────────────────┬───────────┘
                                 │                           │
                        Retailer sites (8)          External APIs:
                        Algolia / Shopify /         COROS Open API,
                        headless-Astro storefronts  Anthropic / OpenAI / Google
```

Three architectural principles show up consistently across the codebase (and are documented inline as such):

1. **API-first / server-computed numbers.** Every derived figure (cost/km, lifetime pace, retirement pct, week-over-week volume, race countdowns) is computed server-side in the services layer so the web UI, MCP tools, and a future mobile client render identical numbers. Frontend components render; they do not recompute.
2. **One sanctioned write path per invariant.** `rotation.log_run()` is the only code that creates run records — manual REST, MCP, and COROS confirm all route through it (and the retired Strava backfill did too). Similarly, `rotation.retirement_pipeline()` is the single source of the 75%-of-limit computation shared by Home and the Shoes page.
3. **MCP parity with REST.** The MCP server's tools are thin adapters over the same services and models the REST routers use; adding a service capability generally means adding both a router endpoint and an MCP tool over the same function.

As of Phase 5 a fourth principle is now realized in the schema itself: **one canonical store per physical fact.** Every physical run — Strava export, COROS sync, manual log — is exactly one row in the `activities` table, discriminated by `source`; shoe attribution is a separate concern (`shoe_runs`). The earlier two-store split (frozen `strava_activities` + data-bearing `shoe_runs`) and its dedup-by-link machinery are gone.

The system is also **self-referential by design**: the embedded assistant (Son of Anton) is an MCP *client* that connects back over HTTP loopback to the MCP server mounted on the same process, so the assistant's capabilities are exactly the MCP tool surface — tool discovery is automatic and there is no second tool registry to maintain.

---

## 2. Technology Stack

### Backend
| Concern | Choice | Notes |
|---|---|---|
| Language / runtime | Python 3.11+ | |
| Web framework | FastAPI 0.109 (Starlette 0.35.1, pinned) | Pin exists to resolve an `mcp[cli]` ↔ `sse-starlette` ↔ Starlette version triangle (documented in `requirements.txt`) |
| ASGI server | Uvicorn 0.34 (`reload=True` dev mode via `run.py`) | Binds `127.0.0.1:8000` by default (R2.1); `API_HOST=0.0.0.0` opts into LAN |
| ORM / DB | SQLAlchemy 2.0.25 → SQLite (`~/anton-data/shoe_deals.db`, out of tree since R2.2) | `check_same_thread=False`; `DATABASE_URL` absolute path |
| Migrations | Alembic 1.13 (batch mode for SQLite) — **sole schema authority (R2.2)** | Startup runs `alembic upgrade head` (`database.run_migrations()`); `create_all` is test-fixture-only; the baseline recreates the pre-Alembic schema. Authoritative list in §5. (`legacy_migrations/` deleted R2.2.) |
| MCP | `mcp[cli]` 1.28.0 — FastMCP server, `ClientSessionGroup` client | Streamable HTTP transport, mounted at `/mcp` |
| AI SDKs | `anthropic`, `openai`, `google-generativeai` | Provider strategy pattern in `chat_service.py` |
| Scraping | `requests`, Playwright 1.41 (sync API), BeautifulSoup4/lxml | Playwright used for JS-heavy pages and Algolia credential rediscovery |
| Data import | pandas ≥ 2.0 (Strava CSV), `zoneinfo` | |
| SSE | `sse-starlette` 1.8.2 | Chat stream + scrape progress stream |
| Scheduling | APScheduler 3.10.4 is a declared dependency | **No scheduler is wired up anywhere in the code** — scraping is manual-trigger only |
| Testing | pytest — one module per feature area; suite green (64 passing as of 2026-07-06 — the live count is authoritative in `docs/changelog.md`'s newest entry and `project_state.md` §2) | |

### Frontend
| Concern | Choice |
|---|---|
| Framework | React 18.3, Vite 5, JSX (no TypeScript) |
| Routing | react-router-dom 6 |
| Server state | TanStack React Query 5 (`hooks/useApi.js`) |
| HTTP | axios with a response interceptor normalizing FastAPI error shapes |
| Styling / UI | Tailwind 3.4, shadcn-style components over Radix primitives (`components/ui/`), lucide-react icons; custom `BrandMark` logo component |
| Charts | recharts |
| Chat rendering | react-markdown; manual `fetch` + SSE frame parsing in `useChatStream.js` |
| Persistence | `localStorage` for chat conversations (`lib/conversations.js`, capped at 50) and checkpoint-prompt dedup (`lib/checkpoints.js`) |

Dev-time coupling: the Vite dev server proxies `/api` to `127.0.0.1:8000` (explicitly IPv4 to dodge Node 18's `localhost` → `::1` resolution). Production expects `VITE_API_URL` to be set; there is no production deployment configuration in the repo.

---

## 3. Folder Structure

```
running-shoe-deals/
├── CLAUDE.md                    # Claude development guide (conventions); the session log is docs/changelog.md
├── QUICKSTART.md, TROUBLESHOOTING.md
├── REDESIGN_PLAN.md, REFACTOR_PLAN.md, STRAVA_IMPORT_REVIEW_TASKS.md,
│   UI_REVIEW_TASKS.md, strava-historical-import-plan.md   # Planning docs (the "§N" references in code comments)
├── docs/                        # The documentation suite (this file, domain_model, design_decisions, …)
│                                #   + changelog.md — the session log (authoritative history, formerly root claude.md)
├── .claude/commands/            # Claude Code project commands (/project:migrate etc.)
├── .playwright-mcp/             # Browser-testing session artifacts (logs/snapshots; not app code)
│
├── backend/
│   ├── run.py                   # Uvicorn entrypoint
│   ├── seed_data.py             # DB seed (retailers + tracked shoes); export.py can regenerate it
│   ├── requirements.txt
│   ├── alembic/ + alembic.ini   # Sole schema authority (R2.2) — authoritative list in §5
│   │                            # (latest: d4e5f6a7b8c9 msrp_drives_deals, 2026-07-06)
│   │                            # legacy_migrations/ deleted R2.2; live DB moved to ~/anton-data/
│   ├── tests/                   # pytest suite — one module per feature area
│   └── app/
│       ├── main.py              # App assembly, CORS, router includes, /mcp mount, lifespan
│       ├── database.py          # Engine, SessionLocal, get_db, init_db
│       ├── mcp_server.py        # FastMCP server: ~20 tools, 7 resources, 1 prompt
│       ├── coros_client.py      # COROS Open API HTTP client (no DB)
│       ├── scrape_runner.py     # Background concurrent scrape job
│       ├── scrape_state.py      # In-memory pub/sub for scrape SSE
│       ├── models/
│       │   ├── models.py        # 12 SQLAlchemy models
│       │   └── schemas.py       # Pydantic request/response schemas
│       ├── routers/             # 17 thin REST routers (see §8)
│       ├── services/            # Domain logic (see §7)
│       ├── scrapers/            # Scraper subsystem (see §10)
│       └── scripts/             # CLI wrappers: import_strava, seed_gear_mappings
│                                # (backfill_strava removed in Phase 5 — its job is done)
│
└── frontend/
    └── src/
        ├── App.jsx              # Route table incl. legacy-bookmark redirects
        ├── pages/               # Home, Training, Deals, MyShoes, ShoeDetail, ChatPage,
        │                        # Settings (nested: tracking / retailers / sync)
        ├── components/          # Feature components + chat/, training/, layout/, ui/ subfolders
        ├── hooks/useApi.js      # React Query hooks per API family
        ├── hooks/useChatStream.js
        ├── services/api.js      # Single axios API client, grouped per domain
        └── lib/                 # conversations, checkpoints, shoeTypes, runSource, utils
```

Notable: `docs/changelog.md` (formerly root `claude.md`) functions as an architecture-decision log; many code comments reference "§N" sections of the planning markdown files at the repo root. These documents are part of the system's institutional memory and should be treated as first-class.

---

## 4. Request Lifecycle

### REST (web UI)
1. Browser → Vite dev proxy (`/api/*` → `127.0.0.1:8000`) or direct in production.
2. FastAPI middleware: CORS (origins from `ALLOWED_ORIGINS`, defaults to localhost:3000/5173).
3. Router handler with `db: Session = Depends(get_db)` — **session per request**, opened and closed by the dependency.
4. Router delegates to a service function (thin-router convention; aggregation/derivation never lives in routers on the newer surfaces — `home`, `activities`, `training`, `races`, `rotation-overview`).
5. Service queries via SQLAlchemy; derived fields computed at this boundary.
6. Pydantic response model serializes (several models use `from_attributes` and read attributes attached dynamically by services, e.g. `attach_derived` on races, `_attach_computed_fields` on owned shoes — and, post-Phase-5, `ShoeRunResponse` reads `ShoeRun`'s property proxies, which resolve through the joined `Activity`).

Most routers are synchronous `def` handlers (FastAPI runs them on a threadpool). The chat, scrape-all, and SSE endpoints are `async`.

### MCP tool call
1. MCP client (Claude Desktop via `mcp-remote`, or Son of Anton's in-process client) → `POST /mcp/` Streamable HTTP. The mount required two deliberate fixes recorded in code: `streamable_http_path="/"` on the FastMCP instance (to avoid `/mcp/mcp`), and running `mcp.session_manager.run()` inside the FastAPI lifespan (mounting a sub-app does not run its lifespan).
2. FastMCP dispatches to the tool function. Tools cannot use FastAPI DI, so each opens its own session via a local `get_session()` context manager mirroring `get_db`'s lifecycle.
3. Tool calls the same service functions as REST, returns plain dicts/lists (with explicit `{"success": bool, ...}` envelopes on write tools).

### Chat message (Son of Anton)
1. `POST /api/chat/message` with the full message history (client-managed state; the server is stateless per request).
2. `stream_chat()` spawns `_run_chat` as an isolated asyncio Task communicating over an `asyncio.Queue` — a deliberate structure to confine anyio cancel scopes inside one task so they never cross the SSE generator boundary.
3. `_run_chat` opens an MCP `ClientSessionGroup`, connects to `MCP_SERVER_URL` (default: this same server's `/mcp`), discovers tools, pre-reads the `shoes://rotation` and `shoes://deals/active` resources and appends them to the system prompt as "live context".
4. The provider (Anthropic/OpenAI/Gemini, routed by model-name prefix) runs an agentic stream/tool-call loop, capped at `MAX_AGENTIC_TURNS = 25`, pushing `{text | tool_call | tool_result | done | error}` events onto the queue.
5. The router wraps the queue in an `EventSourceResponse`; the frontend's `useChatStream` parses SSE frames by hand and renders text + tool indicators incrementally.

### Background scrape (`POST /api/scrape/all`)
1. Handler tries a **non-blocking acquire of a process-wide `threading.Lock`**; returns `{"started": false}` if a scrape of any kind is running.
2. Schedules `run_scrape_job` via FastAPI `BackgroundTasks` and returns immediately. The job — not the handler — owns releasing the lock in a `finally`.
3. The job runs promo detection sequentially, then scrapes **retailers concurrently** (one worker thread each via `asyncio.to_thread`, each with its own DB session; shoes within a retailer stay sequential for rate-limiting and per-scraper credential caching).
4. Progress events are published to `scrape_state` (in-memory pub/sub with full-history replay for late SSE subscribers) and relayed by `GET /api/scrape/stream`.

Single-shoe and single-retailer scrapes remain synchronous request-scoped calls guarded by the same lock (`scrape_guard()` context manager → HTTP 409 on conflict).

---

## 5. Database Architecture

**Engine:** SQLite, single file `backend/shoe_deals.db`, accessed with `check_same_thread=False` and SQLAlchemy's default pooling. No WAL/pragma configuration is set in code.

**Schema management is single-authority (R2.2, 2026-07-07):**
- Alembic is the sole schema source. Startup runs `alembic upgrade head` (`database.run_migrations()`); `Base.metadata.create_all` lives only in the test fixtures. The baseline revision (`cf1eccba0a79`) recreates the exact pre-Alembic schema, so a fresh DB builds entirely from the migration chain — a model edit without a migration no longer silently diverges on the live DB.
- Alembic runs in batch mode (`render_as_batch=True` for SQLite ALTER) with the baseline plus five incremental migrations — **this is the authoritative migration list; other documents cite it rather than counting independently**: `mileage_limit`, the Strava import tables, `planned_races`, `canonical_activities` (`c3d4e5f6a7b8`), and `msrp_drives_deals` (`d4e5f6a7b8c9`, 2026-07-06 — `target_price` relaxed to nullable on `shoes` and `deals`). `canonical_activities` is the model for how structural migrations should be done here: **reversible** (downgrade reconstitutes both old tables), verified against the live DB with pre/post reconciliation (698 runs · 8,028.02 km · 667 attributed · zero per-shoe mileage drift · 933 activities), and preceded by an explicit backup (`shoe_deals.db.bak-pre-activities`).
- The former `legacy_migrations/` pre-Alembic scripts were deleted in R2.2 (git history is the archive).

**The live DB and backups live outside the repo tree** (R2.2): `~/anton-data/shoe_deals.db`, with dated `.bak*` restore points under `~/anton-data/backups/` (convention `shoe_deals.db.<YYYY-MM-DD>-<label>.bak`; see design_decisions E2/A6) — manual file copies taken before each structural migration, an informal but real recovery mechanism.

### Tables (16 models)

**Deal-tracking domain**
- `shoes` — tracked models to monitor. Key fields: `brand`, `model`, `shoe_type`, `msrp` (**the deal driver** since B9-v2 — a deal is any price below it; a shoe without an MSRP cannot produce deals), `target_price` (optional personal threshold, nullable, no longer part of qualification), `is_active`. **Deliberately size-less** — a model is tracked across all sizes.
- `retailers` — `platform` (`shopify` | `algolia` | `custom`) drives dynamic scraper construction; `scraper_config` JSON holds Algolia credentials/selectors; `last_scraped_at`.
- `price_records` — append-only price history per (shoe, retailer, product_url): `price`, `original_price`, `in_stock`, `sizes_available` (JSON list), `image_url`, `colorway`, `scraped_at`.
- `deals` — qualified active deals: prices, savings (measured against MSRP since B9-v2), `sizes_available`, `is_active`, `detected_at`. `target_price` retained as a nullable reference snapshot only — it no longer drives qualification or savings.
- `promo_codes` — per-retailer discount codes, `source` = scraped | manual (manual never overwritten by scraped data).
- `scrape_runs` — durable scrape observability (R2.5): one row per retailer per full-catalog attempt (`status`, counts, `error`), written only by `ScrapeOrchestrator.scrape_retailer`; per-retailer health derived at read time.

**Rotation / training domain (post-Phase-5)**
- `activities` — **the canonical record of every physical activity.** One row per activity regardless of origin, discriminated by `source` (`strava` | `coros` | `manual`); `activity_type` (Run/Ride/Walk/…). Columns are a superset of the old `strava_activities` schema so the frozen bulk-export archive survives intact (`raw_json`, `fit_filename`, cadence, calories, grade-adjusted distance, UTC + America/Toronto timestamps, `run_date` local-date key). External IDs are the dedup/idempotency keys: `strava_activity_id` (unique) for re-imports, `coros_activity_id` for COROS sync. **Pace is stored as integer seconds-per-km**; formatting to `"M:SS/km"` happens only at boundaries. Per-run manual notes live on `description`.
- `shoe_runs` — now a **pure attribution row**: `{id, activity_id (FK, unique), owned_shoe_id, created_at}`. It answers only "which shoe ran this activity"; an activity is attributed to at most one shoe. The table name and the old field names were deliberately retained: read-only **property proxies** (`distance_km`, `run_date`, `source`, `avg_pace`, `avg_hr`, `notes`, `coros_activity_id`) pull from the joined activity so `ShoeRunResponse` and every existing reader keep the identical response shape with zero frontend/MCP changes. (Trade-offs of the proxies are noted in §15 and `dependency_graph.md` §8.)
- `owned_shoes` — personal rotation, **deliberately not the same table as `shoes`**; owning and watching are independent. `starting_mileage`, `current_mileage` (a **stored counter**: starting + Σ attributed distances — explicitly untouched by the Phase-5 restructure), `mileage_limit`, `status` (active | retired | for_sale), `purchase_price` (cost/km derived, never stored), `image_url` override.
- `shoe_notes` — timestamped, mileage-anchored journal (`mileage_at_note` always captured server-side; `triggered_by` = manual | checkpoint).
- `strava_gear_mappings` — exact stripped gear string → owned shoe; nullable `owned_shoe_id` encodes "known but deliberately unmapped". (Historical: consumed by the one-time backfill; retained as the record of those decisions.)
- `planned_races` — races with target time; countdown/target-pace derived at the boundary, never stored.
- `athlete_metrics` — periodic COROS athlete-level fitness snapshots (R2.7 T5): `vo2max`, `threshold_pace_s_per_km`, `race_predictions` JSON; newest read for the Training fitness card.
- `checkpoint_prompts` — records which 100 km-checkpoint note prompts have been shown per owned shoe (R2.6), unique `(owned_shoe_id, checkpoint_km)`. Moved off browser localStorage so a second device doesn't re-prompt; UI-state, not a mileage fact.

**AI / assistant**
- `chat_conversations` — persisted Son of Anton conversations (R2.6): client-UUID PK, `title`, `model`, and both message arrays (`display_messages` = rich UI shape, `api_messages` = LLM shape) as JSON columns. The streaming endpoint stays stateless; a CRUD surface writes here on stream-end. Replaces the former localStorage store (design_decisions C10 ← C8).

**Removed in Phase 5:** the `strava_activities` table and `StravaActivity` model (contents migrated into `activities` with `source='strava'`), and the `strava_backfill` service — the two-store reconciliation it performed is exactly what the migration made permanent.

**Infrastructure**
- `app_settings` — generic key/value store; currently only `last_coros_sync_at`.

### Cross-domain relationships
There is **no foreign key between the deal domain and the rotation domain**. The bridge is a documented heuristic: a "replacement deal" for an owned shoe is any active deal on a tracked `Shoe` whose `shoe_type` string matches. Image matching from `price_records` to owned shoes is likewise a case-insensitive substring heuristic. Both are explicitly labeled as heuristics in code.

---

## 6. Domain Model

Two aggregates, one canonical run store, several enforced invariants:

**Watchlist aggregate** (`Shoe` → `PriceRecord*`, `Deal*`; `Retailer` → `PromoCode*`)
- *Deal qualification invariant* (orchestrator, B9-v2 since 2026-07-06): a deal exists iff the scraped price is **strictly below the shoe's MSRP** (read fresh each scrape so MSRP edits take effect immediately); savings = MSRP − price. A shoe without an MSRP cannot produce deals; the retailer's own compare-at price is no longer consulted.
- *Deal retirement*: two mechanisms — per-URL deactivation when a re-scraped price no longer qualifies, and orphan retirement when a URL stops appearing in a successful non-empty search (guards against renamed shoes leaving zombie deals; a transient empty response cannot wipe deals).

**Rotation aggregate** (`OwnedShoe` → `ShoeRun*` (attributions), `ShoeNote*`; each attribution → one `Activity`)
- *Canonical-run invariant (new)*: every physical run is exactly one `Activity` row; `shoe_runs.activity_id` is unique, so an activity has at most one shoe attribution. There is no dedup-by-link anymore because there is nothing to deduplicate — the old MATCH/BACKFILL machinery retired with the migration.
- *Mileage invariant*: `current_mileage = starting_mileage + Σ(attributed activity distances)`, maintained as a stored counter. All mutations flow through `rotation.log_run` (creates the Activity, then the attribution, in one flow) and `rotation.delete_run`.
- *Archive-preservation rule (new)*: `delete_run` removes the attribution and decrements mileage, and deletes the underlying activity too — **except** `source='strava'`, whose activities are the frozen bulk-export archive; deleting the attribution merely un-attributes that historical run.
- *Checkpoint semantics*: crossing each 100 km boundary flags `checkpoint_reached` so the UI can prompt a journal entry (prompt-shown state is client-side only, in localStorage).
- *Retirement pipeline*: active shoes at ≥ 75% of `mileage_limit`, worst first — one shared computation (`rotation.retirement_pipeline`) backing both Home alerts and the Shoes page. MCP additionally emits 600/700/800 km advisory thresholds on `log_run_to_shoe`.
- *Dedup invariants*: `activities.strava_activity_id` unique (import idempotency); COROS dedup on `activities.coros_activity_id` with a date+distance-within-0.1 km fallback for pre-feature manual logs.

**Unified activity feed** (`services/activities.py`) — still the single read seam the whole app (web + MCP + future mobile) goes through, and the Phase-5 payoff is visible here: `_build` is now **one pass over `activities` (runs only) LEFT-joined to its optional attribution** for shoe info. No union, no double-count risk by construction. `UnifiedActivity` kept its shape, so `strava_stats`, `home`, and the routers were unchanged by the migration — exactly the seam working as designed.

**Conventions worth knowing**
- Pace now has **one persisted representation**: integer seconds-per-km on `activities`, formatted to `"M:SS/km"` only at boundaries (`rotation.seconds_to_pace`). Residual duplication: the `ShoeRun.avg_pace` property proxy re-implements the formatting inline (models can't import services), and `coros_client` carries a third copy — see §15.
- "Personal bests" are explicitly *whole-activity* times within a distance band, not segment PBs, and the code insists this be described accurately downstream.
- Timezone: America/Toronto is the canonical local zone for run dates (hard-coded in the Strava importer; COROS sync protocol passes it explicitly).

---

## 7. Services Layer

Extracted during the 2026 refactor; the stated rule is that routers and MCP tools are thin adapters and business logic lives here exactly once.

| Service | Responsibility |
|---|---|
| `rotation.py` | The rotation domain's core: `log_run` — the only run-record writer, which now creates the canonical `Activity` (pace converted to seconds, notes onto `description`) then the `ShoeRun` attribution, with `increment_mileage`/`commit` escape hatches for batch callers; `delete_run` (with the strava archive-preservation rule); `add_note`; checkpoint detection; lifetime stats — now a plain mean over `Activity.avg_pace_s_per_km` via the attribution join, no string parsing; `cost_per_km`; `retirement_pipeline`; `active_deal_counts_by_type` (the cross-domain bridge); image matching heuristic; pace conversion helpers. |
| `activities.py` | The canonical run feed (see §6): one query over `activities` runs + attribution join, with year/month/shoe/min-distance filters and stable pagination (deterministic tiebreak key). Still computed fully in Python over all rows. |
| `strava_import.py` | CSV → **`activities` (source='strava')** upsert. Encodes hard-won export facts as executable assumptions: duplicate `Distance` headers (km vs meters) with a self-check assertion, UTC→Toronto conversion (145 evening runs shift days), gear-string stripping. Idempotent on `strava_activity_id`. |
| `strava_gear.py` | Pure-function gear→shoe auto-matcher; deliberately conservative (exact normalized match only; ambiguous/unmatched left for a human). Its one-time consumer (backfill) has retired; retained for any future re-import. |
| *(removed)* `strava_backfill.py` | The two-store MATCH/BACKFILL reconciliation, its CLI, and its tests were deleted in Phase 5 — the migration made its work permanent. Its design (plan-then-execute, per-shoe mileage policies, human-gated ambiguity) remains documented in `docs/changelog.md` and the planning docs as precedent. |
| `strava_stats.py` | Weekly/monthly training summaries (distance-weighted pace via total moving time) and distance-band bests, over the canonical feed. |
| `coros.py` + `coros_client.py` | Server-side COROS sync path: fetch running activities from the COROS Open API, two-tier dedup **against `activities.coros_activity_id`**, confirm → `rotation.log_run(source="coros")`, stamp `last_coros_sync_at`. Client is HTTP-only, config from env vars; absence of credentials means the feature is cleanly disabled rather than erroring. |
| `home.py` | Assembles the four Home attention modules (training pulse, shoe alerts, top deals, activity strip) in one pass; explicitly budgeted (< 200 ms target) as the future mobile launch screen. |
| `races.py` | Derived race fields (countdown, target pace) attached at the boundary; shared by router and MCP so both report identical numbers. |
| `settings.py` | Thin key/value accessor over `app_settings`; `set_setting` deliberately does not commit (caller owns the transaction). |
| `chat_service.py` | The AI layer (see §9). |

Transaction ownership is heterogeneous by design: `rotation` functions commit themselves (with opt-outs), `DealStore` methods each own commit/rollback, `set_setting` never commits.

---

## 8. API Layer (REST)

Seventeen routers under `/api`, all behind the shared bearer token (R2.1 — see §11). Grouped by maturity/pattern:

**Newer, service-backed, aggregate-per-page endpoints** (the "API-first" pattern):
- `GET /api/home` — all four Home modules in one round trip.
- `GET /api/watchlist` — every tracked shoe with best active deal, best-ever price, and last-seen price per retailer, pre-sorted for the Deals page split; deliberately one endpoint, with the in-Python reduction justified by personal scale.
- `GET /api/activities` — canonical run feed with filters/pagination.
- `GET /api/training/summary|records`, `GET /api/races` (+ CRUD), `GET /api/owned-shoes/rotation-overview` (id-keyed, lightweight — the page merges it with full shoe rows client-side).
- `GET /api/strava/status` — import health for Settings; post-Phase-5 it reports over `activities` filtered to `source='strava'`.

**Domain CRUD**: `shoes` (incl. scrapability dry-run test), `retailers` (incl. promo CRUD), `deals` (list/deactivate), `owned-shoes` (CRUD + log-run + runs + notes + replacement-deals + COROS sync sub-routes under `coros_sync.py`).

**Operations**: `scraping` (sync per-shoe/per-retailer, background `/all` + `/stream` SSE, promo detection, three no-DB scraper smoke-test endpoints), `admin` (one-off kids-shoe cleanup), `export` (regenerates `seed_data.py` from the live DB — a code-as-backup mechanism), `dashboard` (legacy stats still used by Layout/Settings).

**Chat**: `/api/chat/providers` (availability driven by API-key presence; model catalogs hard-coded here), `/chat/resources` (@-mention picker data), `/chat/resource/read` (proxy to MCP resource read), `/chat/message` (SSE stream).

Response-shape conventions: Pydantic response models on most endpoints; a few newer ones (`rotation-overview`, `replacement-deals`) return shaped dicts. Run-shaped responses (`ShoeRunResponse`) survived the Phase-5 restructure unchanged because they now read through `ShoeRun`'s activity proxies. One documented breaking change remains on the books: `POST /{id}/log-run` returns a `LogRunResponse` envelope rather than the bare shoe.

---

## 9. AI Layer

Two complementary AI surfaces share the MCP server as their common substrate:

### The MCP server (`app/mcp_server.py`)
All four MCP primitives are implemented:
- **Tools (~20):** deals (get/get-by-shoe), tracked shoes (list/add/delete), retailers, `trigger_scrape` (real synchronous scrape, lock-aware, refuses concurrency rather than queueing), dashboard stats, price history, full rotation suite (owned shoes, runs, log/confirm/delete, notes, retire), COROS sync pair (`fetch_unsynced_coros_runs` / `confirm_coros_run`), training analytics (`get_training_summary`, `get_personal_bests`, `get_planned_races`), and `draft_shoe_review` — which uses **MCP sampling** (server → client `create_message`) to have the *client's* LLM draft a review from journal notes, degrading gracefully when the client doesn't support sampling.
- **Resources (7):** static (`shoes://rotation`, `shoes://deals/active`, `shoes://retailers`) and templated (`shoes://owned/{id}`, `/{id}/runs`, `/{id}/notes`, `shoes://deals/{brand}`, `strava://runs/{year}/{month}` — the last designed so a chat can pull one month without flooding context; post-Phase-5 these read the canonical `activities` rows). Each resource returns **markdown + embedded JSON payload** — human-readable and machine-parseable in one body.
- **Prompt (1):** `sync_coros_runs` — a full agent protocol (fetch via the *external* COROS MCP connector, dedup against logged runs, suggest shoes by pace-primary/distance-secondary signals, present-then-wait-for-confirmation, log, summarize, threshold check). This encodes the COROS sync workflow as a reusable, client-side agent script.
- **Logging/Context:** tools use `ctx.log` to push advisory notifications (scrape completion, mileage thresholds) through the protocol.

### Son of Anton (embedded assistant)
- Multi-provider via a strategy pattern (`AnthropicProvider` / `OpenAIProvider` / `GeminiProvider`, routed by model-name prefix; default model `claude-haiku-4-5-20251001`). Each provider implements the same streaming agentic loop contract against a shared `call_mcp_tool` closure and event queue.
- **Tool discovery is fully automatic**: the chat service connects as an MCP client to `MCP_SERVER_URL` (its own server by default); a new `@mcp.tool()` becomes a chat capability with zero registry changes.
- Context priming: rotation + active-deals resources are read at conversation start and appended to the system prompt, with explicit system-prompt rules telling the model when to trust that context vs. re-query. The system prompt also encodes behavioral guardrails (verify-before-claiming, check-before-adding, verify tool success, resolve shoe identity by lookup).
- Robustness measures with documented rationale: `MAX_AGENTIC_TURNS` cap (loop-termination guarantee independent of model behavior), isolated-task/queue architecture (anyio cancel-scope confinement), silent-fallback resource loading.
- Conversation state lives entirely in the **browser's localStorage** (50-conversation cap, empty-conversation pruning, quota-overflow trimming). The backend is stateless with respect to chat history.
- A removed integration is worth recording: an earlier attempt to call the external COROS MCP (`https://mcpus.coros.com/mcp`) directly from `chat_service` was removed because that server's OAuth is managed by desktop clients and can't be driven from backend code; the COROS-MCP path lives in Claude Desktop via the `sync_coros_runs` prompt instead.

---

## 10. Scraper Architecture

Decomposed (during the refactor) from one monolithic manager into four modules with a backward-compat shim (`scraper_manager.py`) re-exporting the old names:

```
registry.py ──builds──▶ {retailer name → BaseScraper instance}
     │  bespoke subclasses by name first; else dynamic by Retailer.platform
     ▼
orchestrator.py (ScrapeOrchestrator, aliased ScraperManager)
     │  search → detail → qualify (on_sale AND ≤ target) → retire stale/orphans
     ▼
deal_store.py (DealStore) — all PriceRecord/Deal/PromoCode writes,
                            each method owns commit/rollback
lock.py — process-wide threading.Lock guarding every scrape entry point
```

**Class hierarchy:**
- `BaseScraper` (abstract): requests session + sync-Playwright fetching with per-request sleeps (2–3 s politeness), price/size parsing, stock heuristics (English + French phrases), **kids/junior filtering** applied once in `search_products_filtered` so every subclass inherits it, promo-code extraction (regex heuristics pairing codes with nearby "% off" text), and **Algolia credential rediscovery** — headless Playwright drives the retailer's own search box and intercepts `*.algolia.net` XHR to recover app id/key/index (stripping sort-replica suffixes), enabling self-healing on 401/403.
- `AlgoliaScraper` and `ShopifyScraper`: generic platform bases (Algolia search API; Shopify `/products.json` catalogs).
- Eight bespoke subclasses: The Last Hunt, Altitude Sports (Algolia); JD Sports, Boutique Endurance, Le Coureur, BlackToe Running, ForeRunners (Shopify, with locale quirks); En Route Run (bespoke — headless Astro storefront with all standard Shopify JSON endpoints 404'd; parses inline hydration JSON).
- `platform_detection.py`: on retailer creation, probes `/products.json` to auto-classify shopify vs custom; validates Algolia credential presence; failures never block creation.

**Execution modes:**
1. Synchronous request-scoped (single shoe / single retailer / MCP `trigger_scrape`) — guarded by `scrape_guard()`, 409 on conflict; the frontend gives these calls a 35-minute axios timeout.
2. Background concurrent (`/scrape/all`): per-retailer worker threads, per-thread DB sessions, SSE progress with full-history replay. Documented as an *additional* path reusing the same per-(shoe, retailer) primitive, not a replacement.

Known operational constraints recorded in project docs: full scrapes take 20–30+ minutes and the MCP `trigger_scrape` full-catalog path reliably times out client-side (workaround: per-shoe calls or the web UI); two retailers are unreachable (Cloudflare-protected, custom platform).

**Retailer Status** (relocated here from the changelog's reference tail, 2026-07-06 — this table is S05's required context; update it whenever a retailer is added, fixed, or goes dark):

| Retailer | Platform | Scraper | Notes |
|---|---|---|---|
| The Last Hunt | Algolia | ✅ | index `PRODUCTS_TLH_en-CA` |
| Altitude Sports | Algolia | ✅ | index `PRODUCTS_ALS_en-CA` |
| JD Sports Canada | Shopify | ✅ | |
| Boutique Endurance | Shopify | ✅ | `/en` locale required |
| Le Coureur | Shopify | ✅ | `/en` locale; some titles stay French |
| BlackToe Running | Shopify | ✅ | English-only |
| ForeRunners | Shopify | ✅ | `shop.forerunners.ca` |
| En Route Run | Shopify (headless Astro) | ✅ | inline variant hydration JSON |
| Sport Experts | FGL/Canadian Tire | ❌ future | custom platform |
| Sporting Life | Cloudflare-protected | ❌ blocked | paid unblocking declined on principle (D3) |

_Removed: RunAsYouAre (custom front-end), Adidas & Nike (bot-protected)._

---

## 11. Authentication & Security Posture

**Authentication is a single shared bearer token (R2.1, shipped 2026-07-07 — design_decisions E7, supersedes E1).** Every request to `/api/*` and `/mcp` must carry `Authorization: Bearer <ANTON_SECRET>`; a mismatch or absence returns **401 with an empty body**. Enforced by one app-wide **pure-ASGI** middleware (`app/middleware/auth.py`) — pure-ASGI so SSE and the `/mcp` Streamable-HTTP stream pass through untouched, and app-wide so it covers the mounted `/mcp` sub-app without per-router work. The trust model it defends is an **untrusted process/person on the same LAN** (not the internet, not local root); full threat model and rejected alternatives in `SECURITY_PASS_PLAN.md`.

Facts a due-diligence review must state plainly:

- **Public allowlist (no token):** `GET /`, `GET /health`, `GET /api/health`, and all CORS `OPTIONS` preflight. Everything else — every destructive REST endpoint (delete shoe cascades price history; `DELETE /owned-shoes/{id}` destroys run attributions), the scrape triggers, the admin scrape-lock release, the **MCP write tools**, and `POST /api/chat/message` (the paid-LLM proxy) — is behind the token.
- **The three consumers all send it:** the SPA (baked-in `VITE_ANTON_SECRET`, on the axios interceptor **and** the raw chat `fetch`/scrape-SSE paths — the scrape stream was moved off native `EventSource`, which can't set the header, to a `fetch` reader); Claude Desktop (`mcp-remote --header`); the loopback client (Son of Anton, injected at connect time, scoped to the loopback so the secret never reaches an external MCP server — dependency_graph §8.1).
- The server **binds `127.0.0.1:8000` by default** (`run.py`); `API_HOST=0.0.0.0` is the explicit, now-safe LAN opt-in. The app **fails fast** at startup if `ANTON_SECRET` is unset.
- Secrets live in `backend/.env` (gitignored). The bearer token is *also* baked into the SPA bundle via `VITE_ANTON_SECRET` — accepted under the LAN threat model (the bundle reaches only the trusted single user on the trusted machine; §8 Q1). The provider API keys still never ship to the frontend — the chat proxy pattern holds.
- Scraper-side: a distinct, honest User-Agent is configurable; rate-limiting sleeps are baked into the base scraper. The system deliberately declined to add paid Cloudflare-bypass services.
- Persisted external content (product URLs, scraped promo text, image URLs) is rendered by the frontend; scraped strings are treated as data, and deal links render as outbound anchors.

**Not covered by R2.1 (deliberately):** rate limiting on `/api/chat/message` (a separate R2 item — R2.1 stops *anonymous* spend, not an authenticated client looping); HTTPS/TLS (network layer, remote-access story R5.2 — the token is cleartext on the trusted LAN by accepted design); secret rotation UX / per-client keys (one static secret, rotate via `.env` edit + restart). `/docs` and `/openapi.json` now require the token too.

Net: the security architecture is "trusted LAN, single tenant, one shared secret." Every future step that further increases exposure (remote MCP transport; mobile client; any non-localhost deployment) still builds on this gate.

---

## 12. Data Flow

### Deal pipeline
```
seed_data.py / UI ──▶ shoes, retailers
trigger (UI/REST/MCP) ─▶ lock ─▶ registry ─▶ per-(shoe,retailer):
   search_products_filtered ─▶ get_product_details
   ─▶ DealStore.record_price (append price_records)
   ─▶ qualify: price < msrp (no MSRP → no deal; B9-v2)
        yes ─▶ upsert_deal (refresh image/sizes; re-price on price/target change)
        no  ─▶ deactivate_deal (per-URL)
   ─▶ deactivate_orphaned_deals (URLs absent from this non-empty search)
   ─▶ stamp retailer.last_scraped_at
promo detection (homepage regex heuristics) ─▶ promo_codes upsert
Consumers: Deals page (via /watchlist), Home top-deals, MCP deal tools,
           replacement-deal hints in the retirement pipeline
```

### Run data — every ingestion path converges on `activities`
All three sources produce the same two rows via `rotation.log_run`: one canonical `Activity` (`source` discriminated) + one `ShoeRun` attribution.

1. **Manual**: UI LogRunDialog → `POST /log-run` → `rotation.log_run(source="manual")` → Activity + attribution → checkpoint flag → optional journal prompt.
2. **COROS** (two variants):
   - *Server-side* (optional, env-credential-gated): `coros_client` → COROS Open API → dedup against `activities.coros_activity_id` → user confirms assignments → `coros.confirm_run` → `rotation.log_run(source="coros")` → `last_coros_sync_at` stamped.
   - *Client-side agent* (the currently practiced path, per the `sync_coros_runs` MCP prompt): Claude Desktop reads the external COROS MCP connector, dedups against `get_shoe_runs`, suggests shoes by pace/distance heuristics, waits for confirmation, then calls `confirm_coros_run` on this server.
3. **Strava historical** (completed, one-time): export CSV → `import_strava.py` → activities with `source='strava'` (idempotent on `strava_activity_id`, `raw_json` preserved). The original gear-mapping + backfill reconciliation ran against the old two-store layout and its results were made permanent by the `canonical_activities` migration; re-running the importer against a fresh export remains supported and updates rows in place.

### Read-side convergence
All training-facing reads flow through `activities.unified_activities` — now a single query over the canonical table (runs + attribution join) → Training page, `/training/summary`, `/training/records`, Home training pulse, and the equivalent MCP tools — one seam, one set of numbers.

### Chat data flow
Browser (localStorage history) → `/api/chat/message` → provider loop ↔ MCP tools (loopback) ↔ services ↔ SQLite → SSE back to browser. Resources are additionally pre-injected at conversation start and readable on demand via @-mention pills.

---

## 13. External Integrations & Major Dependencies

| Integration | Direction | Coupling / failure mode |
|---|---|---|
| 8 retailer storefronts (Algolia ×2, Shopify ×5, headless Astro ×1) | outbound scrape | Highest-churn boundary in the system. Mitigations: platform base classes, Algolia self-rediscovery, dynamic scrapers from DB config, per-retailer error isolation, dry-run scrapability testing. Per-retailer status: the table in §10. |
| COROS Open API (`open.coros.com`) | outbound REST | Optional; env-gated; absence = feature disabled, not error. |
| External COROS MCP (`mcpus.coros.com/mcp`) | consumed by Claude Desktop, not by this backend | OAuth constraint documented; backend integration deliberately removed. The `sync_coros_runs` prompt encodes a dependency on that server's tool names/schemas. |
| Anthropic / OpenAI / Google APIs | outbound (chat) | Provider strategy isolates SDK differences; availability surfaced per-key in `/chat/providers`; hard-coded model catalogs are a drift point. |
| Strava bulk export | offline file input | No live Strava API dependency; import now targets `activities` directly; import assumptions (duplicate headers, UTC dates, gear whitespace) codified with a self-checking assertion. |
| Claude Desktop | inbound MCP client via `mcp-remote` | Consumes tools/resources/prompts/sampling. |

Critical library pins with recorded reasons: FastAPI 0.109 + Starlette 0.35.1 + sse-starlette 1.8.2 (dependency-triangle resolution around `mcp[cli]` 1.28.0); uvicorn/httpx bumped to satisfy `mcp[cli]`. Playwright is both a scraping dependency and an operational one (browser binaries required). APScheduler is declared but unused — a dependency without an architecture behind it yet.

---

## 14. Current Strengths

1. **Genuine layering with single-authority logic.** The refactor produced a real services layer; the "one sanctioned write path" for runs and the shared retirement-pipeline computation eliminate whole classes of drift bugs (Home and Shoes literally cannot disagree). Routers and MCP tools are demonstrably thin on the newer surfaces.
2. **API-first, multi-client-ready contracts.** Server-computed derived fields, aggregate-per-page endpoints, and identical numbers across web/MCP position the platform well for the anticipated mobile client — this discipline is the most valuable long-term asset in the codebase.
3. **The seam pattern, proven.** The `activities.py` read seam was designed so its internals could be swapped without callers noticing — and Phase 5 did exactly that: the two-store union became a single canonical-table query while `strava_stats`, `home`, the routers, and every response shape stayed untouched. Designing seams and then cashing them in is now demonstrated practice here, not aspiration.
4. **Migration discipline.** The `canonical_activities` migration is a reference example: reversible downgrade, pre-migration backup, live pre/post reconciliation (run counts, total km, attribution counts, zero per-shoe mileage drift), full test suite green, and UI verification across the affected pages — all recorded in the decision log.
5. **A serious, complete MCP implementation.** All four primitives, sampling, resource templates with dual markdown/JSON payloads, and the self-consuming chat client make the AI surface automatically congruent with the app's capabilities. This is architecture, not a bolt-on.
6. **Data-integrity engineering on ingestion.** Idempotent upserts keyed on stable external IDs, two-tier COROS dedup, raw_json escape hatches, a CSV self-check assertion, and (historically) plan-before-write backfill with human-gated ambiguity — the pipelines are designed around "never silently double-count," and the canonical table now enforces it structurally.
7. **Deliberate concurrency design.** The scrape lock's rationale (unbounded stacked scrapes → "scraping forever"), the replay-on-subscribe SSE state manager with its atomicity comment, per-thread DB sessions, and the cancel-scope-confining chat task are all correct solutions with the reasoning written down.
8. **Institutional memory.** `docs/changelog.md` (the session log) as a decision log, §-referenced planning docs, and unusually explanatory comments make the codebase auditable — this document was possible largely because of that habit.
9. **Graceful degradation as a pattern.** Missing COROS creds disable a feature cleanly; failed resource preloading falls back to tools; missing scrapers skip with warnings; sampling-unsupported clients get an actionable error.

---

## 15. Architectural Weaknesses

Ordered roughly by how much they constrain the "long-term platform" ambition. (Import-level detail for several of these lives in `dependency_graph.md` §§7–10.)

1. ~~**Zero authentication across three mutation surfaces**~~ **RESOLVED (R2.1, 2026-07-07).** A shared bearer token now gates all three surfaces (REST, MCP, chat-as-LLM-proxy) and the default bind moved to `127.0.0.1` — see §11 and design_decisions E7. What remains in this space is *rate limiting* on the LLM proxy (a separate R2 item) and, further out, TLS for any off-machine access (R5.2). The item is kept here (struck through) rather than deleted so the "this dominated everything" history stays visible.
2. **Single-process assumptions baked into operational state.** The scrape lock is a `threading.Lock`; scrape progress is in-memory pub/sub; both silently break under multiple Uvicorn workers or any horizontal move. Fine now, but it's an invisible constraint — nothing enforces or documents "must run with one worker."
3. **The run feed is canonical now, but still computed whole-table in Python.** Phase 5 removed the union/dedup cost, yet `unified_activities` still loads every run row (933 activities and growing) and filters/sorts in Python on every call — and Home calls it too, against its own <200 ms budget. The watchlist endpoint similarly reduces all price records in Python. Both remain explicitly justified at personal scale; the next step is indexed date-range queries against the table that now exists.
4. **The `ShoeRun` proxy layer is a compatibility asset with hidden costs.** The property proxies preserved every response shape through the migration (a real win), but: each proxied "column" read is a lazy `Activity` load — an N+1 pattern in any un-eager-loaded loop over runs; the attributes silently stopped working in SQLAlchemy `filter()` expressions (query-site code must use `Activity` columns — `coros.py` was migrated correctly, future code must know to); and `avg_pace` re-implements pace formatting inside the ORM class, the third copy of that logic (`rotation`, `coros_client`, the proxy).
5. **Dual schema-management tracks.** `create_all` at startup + Alembic + retained legacy scripts means the schema's source of truth is ambiguous: a model edit without a migration "works" on fresh tables and silently diverges on existing ones. The canonical-activities migration shows the right discipline, but the mechanism doesn't require it. The live DB and five backup copies in the working tree compound the ambiguity about what state is canonical.
6. **Stringly-typed cross-domain bridge.** `shoe_type` free strings link owned shoes to replacement deals; brand/model substring heuristics link images. Both are honestly labeled, but as the platform grows they're the classic silent-mismatch surface (a typo'd type yields zero replacement hints with no error). The vocabulary also exists in three places (backend strings, frontend `lib/shoeTypes.js`, MCP docstrings).
7. **Client-held state that arguably belongs to the platform.** Chat conversations (localStorage, device-bound, 50-cap, quota-trimmed) and checkpoint-prompt history live only in one browser — at odds with the multi-client trajectory everything else is designed for.
8. **Scraper fragility is structural, not incidental.** The highest-value data source depends on eight third-party frontends, sync Playwright inside request threads, and regex promo heuristics. The architecture mitigates well (isolation, rediscovery, dry-runs) but there is no scrape-run history table or failure-trend observability — degradation is only visible in logs and `last_scraped_at`.
9. **Drift-prone duplications at the edges.** Hard-coded model catalogs in `chat.py` vs. prefix routing in `chat_service`; MCP threshold messages (600/700/800) separate from the retirement-pipeline threshold; the `scraper_manager` compat shim and the `coros_sync → owned_shoes` router-to-router import lingering past their refactors ("Task D"); APScheduler declared but unused. Individually trivial, collectively the tax of a fast-moving solo project.
10. **Mixed transaction-ownership conventions.** Per-method commits (DealStore), self-committing service calls with opt-out flags (rotation), caller-owned commits (settings, import) coexist. Each is locally reasoned, but a scrape is not atomic (partial results persist on failure — arguably desirable, but it's implicit), and the conventions must be held in the head.

Uncertainty note: this audit read all services, the MCP/chat layer, the scraper framework and orchestration, models, representative routers, and the frontend shell in full (re-verifying every module the Phase-5 migration touched); individual retailer subclass internals, every page component, `schemas.py`, and the test bodies were reviewed structurally rather than line-by-line. Nothing observed suggests those areas deviate from the patterns described.

---

## 16. Recommended Long-Term Improvements

Directional, in dependency order — no implementation detail intended. (Item 3 from the original audit — build the canonical `activities` table — **shipped on 2026-07-04** and has been replaced by its follow-ons.)

1. **Do the security pass before any exposure-increasing feature.** A single shared bearer token covering `/api` and `/mcp`, plus defaulting the bind to loopback, converts the trust model from "network posture" to "application property." Everything on the wishlist that involves remote transports, ChatGPT integration, or mobile sits behind this.
2. ~~**Resolve schema authority.**~~ **Done (R2.2, 2026-07-07):** Alembic is the single source of truth (startup runs `alembic upgrade head`, `create_all` demoted to test fixtures, baseline recreates the pre-Alembic schema), `legacy_migrations/` deleted, and the live DB + backups moved to `~/anton-data/` with a dated-backup convention. design_decisions A6 → Superseded.
3. **Cash in the canonical table on the read side.** `unified_activities` (and Home through it) can now be indexed date-range queries instead of whole-table Python passes; the seam guarantees callers won't notice. Same treatment eventually for the watchlist reduction.
4. **Shrink the `ShoeRun` proxy surface deliberately.** Treat the proxies as a migration bridge, not a permanent API: eager-load the attribution→activity join at every list seam now (killing the N+1), single-source pace formatting in a pure module importable by both models and services, and over time move readers onto `UnifiedActivity`/`Activity` directly so the filter-vs-attribute trap disappears.
5. **Promote the shoe-type bridge from string to reference.** A small controlled vocabulary (lookup table or enum) shared by `shoes` and `owned_shoes` — and served to the frontend — keeps the deliberate no-FK independence between domains while eliminating silent string-mismatch failures in replacement-deal logic.
6. **Make scraping an observable job system.** A persisted scrape-run/attempt record (per retailer: started, finished, products, errors) turns "is Altitude quietly broken?" from log archaeology into a queryable trend — and is the natural substrate if the unused APScheduler dependency ever becomes real scheduled scraping. This also forces a decision on the single-process lock (either document one-worker as a hard invariant or move coordination into the DB).
7. **Move Anton's memory server-side.** ✅ **Done (R2.6, 2026-07-08).** Chat conversations and checkpoint-prompt state now persist in `chat_conversations` / `checkpoint_prompts` (design_decisions C10 ← C8); the assistant is aligned with the API-first, multi-client principle and the backlogged agents (R3) can share conversational context.
8. **Retire the transition scaffolding on a schedule.** The `scraper_manager` shim, the `coros_sync → owned_shoes` private-helper import (Task D), and hard-coded chat model catalogs are each one-session cleanups; batching them into an explicit "debt sweep" keeps the decision-log habit trustworthy. (`dependency_graph.md` §11 sequences these. The changelog's stale overview tail, formerly on this list, was pruned 2026-07-06.)
9. **Codify the invariants this document describes.** The strongest properties here — single run write path, canonical-activity uniqueness, deal-qualification rule, mileage counter identity, the strava archive-preservation rule — are currently enforced by convention plus tests. A short INVARIANTS section (in `CLAUDE.md`, per the final review §3.1) that future work must check against is cheap insurance for a platform intended to outlive any one refactor.

---

*Maintenance note: this document is Anton's primary technical reference, with `docs/dependency_graph.md` as its import-level companion. Update both when a §-numbered plan phase ships, when a table or router is added, and whenever an invariant in §6 changes. Last structural event reflected: the `msrp_drives_deals` migration (2026-07-06; docs reconciled same day).*
