# Running Shoe Deal Finder - Project State 📋

**Last Updated:** 2026-07-04
**Project Status:** Anton redesign — Phase 5 backlog (started)
**Current Focus:** Product images, colorway consolidation, scraper durability + coverage

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

| Command | What it does |
|---|---|
| `/project:run` | Start backend (port 8000) + frontend (port 5173) |
| `/project:scrape` | Trigger scraping via the API |
| `/project:seed` | Seed or sync the database with seed_data.py |
| `/project:migrate` | Run a DB migration (pattern + existing scripts) |
| `/project:add-retailer` | Step-by-step guide to add a new retailer scraper |

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

## 🌐 Retailer Status

See `/project:add-retailer` for the full platform detection checklist and steps to add a new scraper.

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
| Sporting Life | Cloudflare-protected | ❌ blocked | paid unblocking service needed |

_Removed: RunAsYouAre (custom front-end), Adidas & Nike (bot-protected)._

---

## 🎯 Project Overview

**Purpose:** Find deals on running shoes from Canadian retailers
**Tech Stack:** Python FastAPI + React + Vite + Tailwind CSS
**Target Users:** Personal use (Montreal-based runner)

---

## 🏗️ Architecture

### Backend (Python/FastAPI)
- `app/main.py` - FastAPI app setup
- `app/routers/` - API endpoints
  - `shoes.py` - Shoe CRUD
  - `retailers.py` - Retailer CRUD
  - `deals.py` - Deal queries
  - `scraping.py` - Trigger scrapes
  - `dashboard.py` - Statistics
  - `owned_shoes.py` - My Shoes CRUD + run logging
  - `export.py` - Export DB → seed_data.py source
- `app/models/` - Database models + schemas
- `app/scrapers/`
  - `base_scraper.py` - Framework (HTTP, Playwright, Algolia rediscovery)
  - `algolia_scraper.py` - Generic Algolia base (auto credential rediscovery)
  - `shopify_scraper.py` - Generic Shopify JSON base
  - `the_last_hunt.py`, `altitude_sports.py` - Algolia subclasses
  - `jd_sports.py`, `boutique_endurance.py`, `le_coureur.py`, `blacktoe_running.py`, `forerunners.py` - Shopify subclasses
  - `enroute_run.py` - Bespoke (headless Astro)
  - `scraper_manager.py` - Orchestration
- `app/mcp_server.py` - MCP tools (mirrors REST API)

### Frontend (React/Vite)
- `src/pages/` — Dashboard, Deals, Shoes, Retailers, PriceHistory, MyShoes, ShoeDetail
- `src/components/` — DealCard, ShoeProductCard, ColorwaySelector, MileageProgressBar, LogRunDialog, etc.
- `src/services/api.js` - API wrapper
- `src/hooks/useApi.js` - React Query hooks

---

## 📊 Database Schema

### Core deal-tracking tables

**shoes** — brand, model, target_price, notes, is_active (size removed 2026-06-17)
**retailers** — name, base_url, scraping_enabled, last_scraped_at, scraper_config
**price_records** — shoe_id, retailer_id, product_url, price, original_price, in_stock, size_available, image_url, colorway, scraped_at
**deals** — shoe_id, retailer_id, current_price, target_price, savings_amount, savings_percent, product_url, in_stock, image_url, colorway, is_active, detected_at, discount_codes, expires_at

### My Shoes tables

**owned_shoes** — brand, model, nickname, status (active/retired/for_sale), starting_mileage, current_mileage, mileage_limit, purchase_price, image_url, created_at
**shoe_runs** — owned_shoe_id, distance_km, run_date, avg_pace, avg_hr, notes, source (manual/coros)
**shoe_notes** — owned_shoe_id, body, mileage_at_note, triggered_by (manual/checkpoint), created_at

---

## 🔧 API Endpoints

### Shoes
- `GET/POST /api/shoes` · `GET/PUT/DELETE /api/shoes/{id}` · `GET /api/shoes/{id}/prices`

### Retailers
- `GET/POST /api/retailers` · `GET/PUT/DELETE /api/retailers/{id}`

### Deals
- `GET /api/deals` · `GET /api/deals/{id}` · `PUT /api/deals/{id}/deactivate`
- `GET /api/deals/shoe/{shoe_id}` · `GET /api/deals/retailer/{retailer_id}`

### Scraping
- `POST /api/scrape/shoe/{id}` · `POST /api/scrape/all` · `POST /api/scrape/retailer/{id}`
- `GET /api/scrape/test/the-last-hunt` · `/test/altitude-sports` · `/test/jd-sports`

### My Shoes
- `GET/POST /api/owned-shoes` · `GET/PUT/DELETE /api/owned-shoes/{id}`
- `POST /api/owned-shoes/{id}/log-run` · `GET /api/owned-shoes/{id}/runs`
- `DELETE /api/owned-shoes/runs/{run_id}`
- `GET/POST /api/owned-shoes/{id}/notes` · `DELETE /api/owned-shoes/notes/{note_id}`

### Export & Dashboard
- `GET /api/export/seed-data` · `GET /api/dashboard/stats` · `/best-deals` · `/recent-deals`

---

## 🔗 Useful Links

- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Frontend:** http://localhost:5173
- **Database:** `backend/shoe_deals.db`

---

**Note:** Update this file after each development session. Session changelogs go at the top.
