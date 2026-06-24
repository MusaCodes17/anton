# Running Shoe Deal Finder - Project State 📋

**Last Updated:** 2026-06-24  
**Project Status:** Phase 5 In Progress  
**Current Focus:** Product images, colorway consolidation, scraper durability + coverage

---

## 🆕 Run pace/HR, lifetime averages, run deletion — 2026-06-24

**[ADDED] avg_pace/avg_hr wired through properly, lifetime stats, and the ability to remove a logged run.**
- `log_run_to_shoe` (MCP) gained `avg_pace`/`avg_hr` params, saved directly to the existing
  `shoe_runs` columns — there was no notes-stuffing workaround to remove, those columns were
  simply unused by the tool until now. `POST /api/owned-shoes/{id}/log-run` already accepted both
  fields (they're on `ShoeRunCreate`/`ShoeRunBase`); nothing needed to change there.
- New computed (non-column) fields on `OwnedShoeResponse`: `lifetime_avg_pace`, `lifetime_avg_hr`,
  `total_runs`. Pace strings are averaged correctly — each "M:SS/km" is converted to seconds,
  averaged, then formatted back (`_pace_to_seconds` / `_seconds_to_pace` in
  `routers/owned_shoes.py`); averaging the strings directly would be meaningless. Computed by
  `_compute_lifetime_stats` + attached via `_attach_computed_fields`, called from every
  `owned_shoes.py` endpoint that returns a shoe (list/get/create/update/log-run/delete-run) so the
  stats are never stale in a response. Also exposed in the `get_owned_shoes` and `get_shoe_runs`
  MCP tools (the latter now returns `{runs, lifetime_avg_pace, lifetime_avg_hr, total_runs}`
  instead of a bare list — MCP-only, the REST endpoint shape didn't change).
  Frontend shows it as a compact line ("Avg pace 3:52/km · Avg HR 152 bpm · 2 runs") in the My
  Shoes detail dialog, only when `total_runs > 0`.
- **[ADDED]** `DELETE /api/owned-shoes/runs/{run_id}` — deletes the run and subtracts its
  `distance_km` back out of the parent shoe's `current_mileage` (floored at 0), returns the
  updated shoe. New MCP tool `delete_shoe_run(run_id)` mirrors it. Frontend: a Trash icon per row
  in the run history table, with a confirmation dialog quoting the exact km that will be
  subtracted. `useDeleteShoeRun` (`hooks/useApi.js`) optimistically patches the runs list and the
  shoe's `current_mileage`/`total_runs` in the query cache in `onMutate` (before the request
  resolves), then re-syncs with the server in `onSettled` either way. The My Shoes detail dialog
  now looks up its shoe live from the shoes list by id (`detailShoeId`, not a snapshot object) so
  it reflects this optimistic update immediately instead of showing stale mileage until reopened.
- Verified live: logged two runs via REST with paces 3:50/km and 4:10/km → lifetime average
  correctly computed as 4:00/km (not a string-average); deleted one run via REST and via the MCP
  tool directly, both correctly subtracted that run's distance from `current_mileage` and
  recomputed `total_runs`/lifetime averages. Frontend production build passes clean.

---

## 🆕 My Shoes UI polish — 2026-06-24

**[ADDED] Search, active/retired split, compact mileage text, and product images on owned shoe cards.**
- Renamed the "Shoes" nav tab to **"Tracked Shoes"** (`Layout.jsx`) to disambiguate from "My Shoes".
- My Shoes page (`MyShoes.jsx`) now has a client-side search bar (brand/model/nickname, no API
  call) and splits cards into an **Active** section (active + for_sale) and a **Retired** section
  below a divider — same card component (`ShoeCard`) for both, just filtered into two grids.
- `MileageProgressBar` gained a `compact` prop: cards now show "Current Mileage: X km" instead of
  "X km" + "Y km limit" (the bar color already communicates the limit). The detail dialog keeps
  the full non-compact version.
- **Images on owned shoe cards**, same placeholder pattern as the Tracked Shoes page (repeating-
  gradient grey box + Footprints icon when there's no image — never a broken `<img>`). Priority:
  manual `image_url` (new nullable column on `owned_shoes`, migration
  `backend/migrate_add_owned_shoe_image.py`) → best-effort `matched_image_url` → placeholder.
  `OwnedShoeForm` gained an "Image URL" field as the manual-upload mechanism — consistent with
  every other image field in this app (`price_records.image_url`, `deals.image_url`), which are
  all CDN URL strings; there's no file-upload backend anywhere to extend instead.
- `matched_image_url` is computed in `owned_shoes.py`'s `GET /` and `GET /{id}` only (not on
  create/update — the list refetch after a mutation picks it up): best-effort lookup against
  `price_records.image_url` where the colorway text contains the owned shoe's model, OR the
  record's `shoe_id` points to a tracked `Shoe` whose brand+model both match (case-insensitive
  substring). No FK between `owned_shoes` and `shoes`, so this is a heuristic, not a join — skipped
  entirely if a manual `image_url` is already set.
- Verified live: an owned "Adidas Adizero Boston 13" picked up a real scraped CDN image; a made-up
  brand/model got `null` (no broken image); a shoe with a manual `image_url` set correctly skipped
  the lookup. Frontend production build passes clean.

---

## 🆕 "My Shoes" personal rotation tracker — 2026-06-24

**[ADDED] Track owned shoes (mileage, notes, run history) — separate from deal tracking.**
- New tables `owned_shoes` + `shoe_runs` (`models.py`), created automatically by `init_db()` on
  next backend start (brand-new tables, so no `ALTER TABLE` migration script was needed —
  `Base.metadata.create_all` only creates what's missing). Deliberately **not** the same table
  as `Shoe` (deal tracking) — owning a shoe and watching it for deals are independent concepts.
- Backend: `app/routers/owned_shoes.py` — full CRUD + `POST /{id}/log-run` (accumulates
  `current_mileage`) + `GET /{id}/runs` (history). `current_mileage` starts equal to
  `starting_mileage` on create, so a partially-worn shoe can be added directly (e.g. 400km in).
  `shoe_runs.source` is `"manual"` for now; `"coros"` is reserved for the not-yet-built COROS
  sync (next session) so it can slot in without a schema change.
- MCP: 5 new tools in `mcp_server.py` — `get_owned_shoes`, `get_shoe_runs`, `log_run_to_shoe`,
  `update_shoe_notes`, `retire_shoe` — same thin-wrapper-over-the-DB pattern as existing tools.
- Frontend: new "My Shoes" page (`pages/MyShoes.jsx`) + nav item, `OwnedShoeForm.jsx`,
  `LogRunForm.jsx`, `MileageProgressBar.jsx` (green <500km / yellow 500–800km / red >800km —
  800km is a hardcoded personal limit, not yet user-configurable). Card grid mirrors the
  existing Shoes page's card pattern; detail dialog shows notes + a run-history table.
- Verified live end-to-end: added Adidas Adizero Adios Pro 4 at 400km starting mileage, logged a
  21.1km run, confirmed `current_mileage` updated to 421.1 and the run appeared in history via
  both the REST API and the MCP tool list (12 tools total, 5 new). Frontend production build
  passes clean.

---

## 🆕 Sporting Life investigated — blocked by Cloudflare, not added — 2026-06-22

**[BLOCKED] Sporting Life (sportinglife.ca) cannot be scraped without a paid unblocking service.**
- Ran the same platform-detection pass used for En Route Run. Unlike that case, the blocker
  isn't the Demandware platform — the entire site sits behind a **Cloudflare managed JS
  challenge**. Plain HTTP requests to any path, including `/robots.txt`, return `403` with a
  "Just a moment..." challenge page.
- Tried a real headless Chromium (via the project's own Playwright, the same engine used for
  Algolia credential rediscovery) with full JS execution and `networkidle` wait — still stuck
  on the challenge. Cloudflare's bot-management fingerprints headless automation itself, not
  just missing JS.
- Same bucket as Adidas, Nike, and MEC (already excluded/removed for being bot-protected) —
  not the "needs a bespoke parser" bucket En Route Run was in. Getting past this reliably would
  need a paid proxy/unblocking service (e.g. ScraperAPI, Bright Data) or fingerprint-evasion
  tooling, a different order of cost/effort than a normal new-retailer scraper.
- **Not added.** No retailer row, no scraper file. Table below updated to reflect why.

---

## 🆕 New retailer — En Route Run (headless Shopify, JSON-LD doesn't have enough) — 2026-06-22

**[ADDED] `EnRouteRunScraper`** (`app/scrapers/enroute_run.py`), registered in `ScraperManager`.
- Site is Shopify-backed (`cdn.shopify.com` / `myshopify.com` in page source) but runs a
  **headless Astro storefront** — none of the usual Shopify endpoints work: `/products.json`
  404s, `/products/<handle>.js` 404s, `/search/suggest.json` is unusable. So it's neither
  plug-and-play `ShopifyScraper` nor Algolia; needed a bespoke scraper.
- The page's `<script type="application/ld+json">` `Product` block has price/availability per
  variant but **no `compareAtPrice`**, so it can't tell a real markdown from full price.
  Instead, every page (product pages *and* `/search?q=` results) embeds the Shopify Storefront
  API's variant data inline as HTML-entity-encoded Astro/Qwik hydration JSON
  (`&quot;availableForSale&quot;:[0,true]…&quot;price&quot;…&quot;compareAtPrice&quot;…`).
  `_parse_variant_blocks()` unescapes + regex-parses these blocks directly (no JSON endpoint
  needed) — same block also gives the "Colour / Size" variant title, parent product title +
  handle, and image. Blocks repeat several times per page (buy box, recommendation widgets) so
  results are deduped by `(handle, variant_title)`.
- `get_product_details` applies the same available-variants-only price logic as the Shopify
  variant-price fix above (prefers cheapest available variant with a real markdown, falls back
  to cheapest available full price). `search_products` parses `/search?q=` result cards
  (`<a href="/products/...">` + adjacent `<img alt="... product image">`) for discovery, same
  brand/model token-matching convention as the other scrapers.
- Verified live: Adidas Adizero Adios Pro 4 — men's $225 (was $300), women's $210 (was $300),
  both genuine markdowns, both flowed through as real deals end-to-end.

---

## 🆕 Stale data after shoe rename — 2026-06-19

**[FIXED] Renaming a shoe's brand/model left old scraped data displayed under the new name.**
- Root cause: `PUT /api/shoes/{id}` (`shoes.py`) overwrote `brand`/`model` with no side effects.
  Deals/price_records are keyed by `shoe_id`, not by what was actually scraped, so renaming
  (e.g. Asics "Magic Speed 4" → "Magic Speed 5", Brooks "Hyperion 3" → "Hyperion Elite 6")
  left deals from the *old*, correctly-matched model name still active — now displayed
  mislabeled as the new model. Verified live: both "new" models don't exist at any retailer yet
  (`search_products` returns 0 hits); the displayed cards were stale prior-model data.
- Fix (`shoes.py` `update_shoe`): when `brand` or `model` changes, all active deals for that
  shoe are deactivated immediately so a rename can't keep showing the previous model's data.
- Cleanup: deactivated the 8 already-affected stale deals; re-scraped to confirm no new
  (incorrect) deals were created.

---

## 🆕 Scrapability check — auto-check removed, manual test retained — 2026-06-19

**[OPTIMIZED] Removed auto-scrapability check on Shoes page load.**
- Root cause: the Shoes page (`frontend/src/pages/Shoes.jsx`) ran a concurrency-limited
  `useEffect` that called `POST /api/shoes/test` for every active shoe on every load — each
  test sequentially hits all scraping-enabled retailers, so a list of ~20+ shoes meant the page
  stayed in a "Checking…" state for minutes and issued a large burst of real requests against
  external retailer sites on every visit.
- **[REMOVED]** The auto-check `useEffect`, the per-shoe `scrapability` state map, and the
  "Scrapeable" status-badge column from the Shoes table.
- **[RETAINED]** The "Test Scrapability" button + `ScrapabilityTestModal` on the add/edit shoe
  form (`ShoeForm.jsx`) — unchanged, still tests on demand before/without saving.
- **[ADDED]** A per-row "Test" icon button (flask icon) in the Shoes table Actions column —
  on-demand only, calls `POST /api/shoes/test` for that one shoe and reuses
  `ScrapabilityTestModal` to show the breakdown + a Re-test button. Never fires automatically.
- Backend (`POST /api/shoes/test`, `ScraperManager.test_shoe_scrapability`) unchanged — it was
  always on-demand; only the frontend's auto-invocation was removed.
- Result: Shoes page now loads immediately (table renders with the existing shoe-list query
  only, no bulk scrapability calls); validation still happens exactly where it matters — when
  adding/editing a shoe, or via the optional per-row "Test" button.

---

## 🆕 Shopify variant-price fix — 2026-06-18 (phantom deals from sold-out sale colorways)

**[FIXED] Phantom deals from Shopify's product-level price ignoring stock.**
- Root cause: Shopify's product-level `price` field is the **minimum price across all
  variants, including sold-out ones**. A sale colorway (e.g. $150, `compare_at_price` $300)
  could be completely sold out while other colorways remained in stock at full price ($300) —
  but the scraper read the product-level $150 alongside `available: true` (true because of the
  in-stock full-price colorways), creating a deal nobody could actually buy. Verified live:
  BlackToe's `adidas-womens-adizero-adios-pro-4` has six sale-priced colorways ($150–$180,
  `compare_at_price` $300) all `available: false`, while every in-stock variant is $300 full price.
- Fix (`shopify_scraper.get_product_details`): price/original_price are now derived from
  **available variants only** — prefers the cheapest available variant with a real markdown
  (`compare_at_price > price`); falls back to the cheapest available full-price variant if none
  of the in-stock variants are on sale. Keeps `in_stock` and `price` referring to the same
  variant pool instead of two different ones.

---

## 🆕 Deal detection fix — 2026-06-18 (require actual markdown, not just target hit)

**[FIXED] Deals were created for full-price items that merely hit the target price.**
- Root cause: `scraper_manager._create_deal`'s trigger was `price <= shoe.target_price` only —
  no check that the retailer was actually discounting. Since most shoes' `target_price` in seed
  data sits at/near MSRP, full-price listings across every retailer qualified as "deals" with
  0% savings (e.g. Adidas Adizero Adios Pro 4 at BlackToe Running: $300 full price, no
  `compare_at_price`, target also $300 → false deal). Verified live via BlackToe's
  `/products/<handle>.js` endpoint.
- Fix (`scraper_manager.py`): a deal now requires `on_sale` (`original_price` present and
  `> price`) **in addition to** `price <= target_price`. Hitting your target at full price no
  longer creates a deal.
- Cleanup: deactivated 185 of 268 existing active deals that had no real markdown (DB backup:
  `backend/shoe_deals.db.bak_pre_dealfix`). 83 genuine markdown-based deals remain.

---

## 🆕 Phase 5 — 2026-06-18 (images, colorway consolidation, rediscovery, +3 retailers)

**Task 2 — Product images + colorway (data foundation).**
- New nullable columns `image_url` + `colorway` on `price_records` **and** `deals`
  (migration `backend/migrate_add_images.py`, idempotent `ALTER TABLE ADD COLUMN`; backup `.db.bak`).
- Scrapers now return both fields: Algolia (`image_url` = S3 CDN URL; colorway from the
  `thumbnails[].color_name` matching the primary image), Shopify (`image`/`featured_image`,
  protocol-relative URLs normalized to `https:`; colorway from the product's Color option).
- `scraper_manager` threads them into `_record_price` + `_create_deal` (existing deals backfill
  images on re-scrape even when price is unchanged). Dashboard + price-history endpoints expose them.
- Schemas: added to `PriceRecordBase` + `DealBase` → flow through `DealResponse` to the UI.

**Task 3 — Colorway consolidation UI (client-side grouping).**
- `Deals.jsx` groups active deals by `shoe_id` → **one card per model** instead of N near-identical
  cards (Boston 13's colorways/retailers now consolidate into a single card).
- New `ShoeProductCard.jsx` (large primary image, price/savings, promo, retailer + buy link) and
  `ColorwaySelector.jsx` (thumbnail gallery; clicking switches the active colorway/retailer).
  `DealDetailModal` now shows the product image too. Placeholder icon when image is null
  (old image-less deals still render).

**Task 1 — Automatic Algolia credential rediscovery (durability).**
- `base_scraper.discover_algolia_credentials(homepage_url, search_selector)` drives the site's own
  search with headless Playwright and intercepts the `*.algolia.net` request to recover the app id,
  search key, and (base, replica-stripped) index name.
- `algolia_scraper._algolia_query` detects HTTP 401/403, rediscovers **once per session**, caches
  the new creds in-memory, retries, and logs a WARNING to update the hardcoded defaults. Graceful:
  returns `[]` (never throws) if rediscovery fails. **Verified** by injecting a bogus key → 403 →
  rediscovery → recovery → 5 results.

**Task 4 — +3 Shopify retailers, list reconciled.** See the retailer platform table below.
Scrapers now live (6): The Last Hunt, Altitude Sports (Algolia); JD Sports Canada,
**Boutique Endurance, Le Coureur, BlackToe Running** (Shopify). Also fixed Shopify size extraction
to locate the "Size" option by name (Le Coureur has a 3rd Width option that broke the old
`split('/')` heuristic).

---

## 🌐 Retailer Platform Analysis (Task 4)

Detection checklist for any new retailer:
- **Shopify?** → `GET /products.json` returns JSON · `/search/suggest.json?q=…` returns products ·
  homepage has `cdn.shopify.com` / `Shopify.theme` / `myshopify`. → subclass `ShopifyScraper`.
- **Algolia?** → DevTools/Playwright shows XHR to `*.algolia.net` with `x-algolia-*` headers. →
  subclass `AlgoliaScraper` (discover creds via the rediscovery helper).
- **FGL/Canadian Tire** (Sport Experts, Sport Chek) or **Custom/brand** (Adidas, Nike, MEC) →
  needs a bespoke scraper; leave `scraping_enabled=False`.

| Retailer | Platform | Scraper | Notes |
|---|---|---|---|
| The Last Hunt | Algolia | ✅ | index `PRODUCTS_TLH_en-CA` |
| Altitude Sports | Algolia | ✅ | index `PRODUCTS_ALS_en-CA` |
| JD Sports Canada | Shopify | ✅ | |
| Boutique Endurance | Shopify | ✅ | `/en` locale required |
| Le Coureur | Shopify | ✅ | `/en` locale; some titles stay French |
| BlackToe Running | Shopify | ✅ | English-only |
| ForeRunners | Shopify | ✅ | `shop.forerunners.ca`; suggest.json occasionally 503s (transient) |
| En Route Run | Shopify (headless Astro) | ✅ | no `/products.json`/`.js`/`suggest.json` — parses inline variant hydration JSON instead, see changelog |
| Sport Experts | FGL/Canadian Tire | ❌ future | custom platform |
| Sporting Life | Salesforce Commerce Cloud / Demandware | ❌ blocked | Cloudflare managed JS challenge on every page (even `/robots.txt`) — 403s plain requests AND headless Playwright (fingerprinted as bot). Not a "needs a parser" case like En Route Run; would need a paid unblocking/proxy service to get past. See 2026-06-22 changelog. |

_Removed retailers (no longer tracked): RunAsYouAre (custom front-end), Adidas & Nike (brand sites, bot-protected)._

**Keeping the DB in sync with seed_data.py:** `RETAILERS`/`SHOES` in `backend/seed_data.py` are the
source of truth. `python seed_data.py` inserts anything missing (additive, safe);
`python seed_data.py --sync` reconciles fully — inserts missing **and deletes** retailers/shoes not
listed (cascades to their price_records/deals). Newly-added retailers are platform-detected; Shopify/
Algolia ones get a scraper subclass + registration immediately.

---

## 🆕 Session Changelog — 2026-06-18 (scraper migration + new retailers)

**The Last Hunt migrated off CSS selectors → Algolia API.**
- Root cause recap: TLH is a Next.js storefront; products render client-side, so CSS scraping found nothing.
- Discovered (via Playwright network interception) that TLH's catalogue is a **commercetools** backend exposed through a **public Algolia** index its own frontend queries. One Algolia request returns name, price, original price, stock (`quantity_left`) and available sizes — no browser, no HTML parsing.
- New `app/scrapers/algolia_scraper.py` — generic `AlgoliaScraper` base (mirrors the `ShopifyScraper` pattern). `the_last_hunt.py` is now a thin subclass holding only its public Algolia app id / search key / index (`PRODUCTS_TLH_en-CA`).
- Verified live: Saucony Endorphin Pro 4 found at **$185.99 (was $299.99)**, in stock, 8 sizes. Returns 0 (correctly) for models TLH doesn't carry.

**Altitude Sports wired up (new retailer).**
- Altitude shares TLH's parent company and runs the **identical Next.js + commercetools + Algolia stack**, so it reuses `AlgoliaScraper`. New `app/scrapers/altitude_sports.py` (index `PRODUCTS_ALS_en-CA`); registered in `ScraperManager`.
- Verified live: Altitude carries the **Adidas Adizero Boston 13** (5 hits) and Saucony Endorphin (13 hits).

**Shopify survey result: JD Sports is the only Shopify retailer.**
- Probed Altitude, Sport Experts, MEC, Running Room, Sport Chek for Shopify fingerprints (`/products.json`, `suggest.json`, `cdn.shopify.com`). **None are Shopify.** Sport Experts + Sport Chek are the FGL/Canadian Tire platform; MEC is custom (403s bots); Running Room serves HTML only.
- Those 4 have no scraper, so `scraping_enabled` was set to **False** (seed + live DB) to stop "No scraper implemented" noise on every scrape. Re-enable any from the Retailers page once a scraper exists.

**Scrapers now live (3):** The Last Hunt (Algolia), Altitude Sports (Algolia), JD Sports Canada (Shopify). Added `GET /api/scrape/test/altitude-sports`.

---

## 🆕 Session Changelog — 2026-06-17 (all 4 critical bugs fixed)

**[FIXED] Issue 1 — Removed `size` field from Shoe model.**
- Why: a single exact size (e.g. "10.5") made the scraper miss the model when that size was out of stock.
- Changes: dropped `size` column (`models.py`), removed it from `ShoeBase`/`ShoeUpdate` (`schemas.py`), the `ShoeForm`/`Shoes` table/deal cards (frontend), `seed_data.py`, `dashboard.py` best/recent deals, and `view_db.py`. Dedup is now brand+model.
- Migration: `backend/migrate_remove_size.py` (idempotent `ALTER TABLE shoes DROP COLUMN size`, SQLite ≥3.35). Ran against existing DB — 12 shoes preserved. Backup at `shoe_deals.db.bak`.
- `PriceRecord.size_available` now means "at least one size in stock" rather than "our exact size".

**[FIXED] Issue 2 — Target-price changes now persist into deals.**
- Root cause: the PUT endpoint + React Query invalidation were actually correct; the bug was in deal detection. Existing deals never had their `target_price`/savings refreshed, and deals were never deactivated when the target dropped below the current price.
- Changes (`scraper_manager.py`): `_create_deal` now also updates `existing_deal.target_price` and recomputes savings whenever price **or** target changed; new `_deactivate_deal()` retires a deal when the scraped price is above the current target. Deal detection always reads the freshly-loaded `shoe.target_price`.
- Verified: raise target above price → deal deactivates; restore → deal reappears with recomputed savings.

**[FIXED] Issue 3 — Export DB back to `seed_data.py`.**
- New endpoint `GET /api/export/seed-data` (`app/routers/export.py`) renders current retailers + shoes as runnable, valid `seed_data.py` source (text/plain).
- Frontend: "Export seed data" button on the Shoes page downloads `seed_data.py`.

**[FIXED] Issue 4 — JD Sports scraper (Boston 13 now found).**
- Root cause: JD Sports Canada (jdsports.ca) is a **Shopify** store; The Last Hunt is a **Next.js** app. The old CSS-selector scraper found nothing, and JD Sports had no scraper at all.
- Changes: new generic `ShopifyScraper` (`app/scrapers/shopify_scraper.py`) using Shopify JSON endpoints (`/search/suggest.json`, `/products/<handle>.js`) — far more reliable than CSS. `JDSportsScraper` (`app/scrapers/jd_sports.py`) extends it; registered in `ScraperManager` under `"JD Sports Canada"`. Added `GET /api/scrape/test/jd-sports`.
- Verified live: Boston 13 found at **$105 (was $190)**, in stock → creates a deal vs the $110/$150 target.
- ⚠️ The Last Hunt remains a Next.js site; its CSS scraper is still unreliable (see Known Issues). Other Shopify retailers (Altitude, etc.) can reuse `ShopifyScraper`.

---

## 🎯 Project Overview

**Purpose:** Find deals on running shoes from Canadian retailers  
**Tech Stack:** Python FastAPI + React + Vite + Tailwind CSS  
**Target Users:** Personal use (Montreal-based runner)  
**Status:** Fully functional, undergoing refinement

---

## ✅ Completed Features

### Phase 1: Backend API ✅
- FastAPI REST API with 20+ endpoints
- SQLite database with proper relationships
- CRUD operations for shoes, retailers
- Deal detection logic
- Dashboard statistics
- Proper error handling and logging

### Phase 2: Web Scraping ✅
- Base scraper framework
- The Last Hunt scraper implementation
- Price extraction and storage
- Automatic deal detection
- Rate limiting and ethical scraping
- ScraperManager orchestration

### Phase 3: React Frontend ✅
- Dashboard with stats and recent deals
- Deals listing with filters and sorting
- Shoe management (CRUD)
- Retailer management
- Dark mode support
- **NEW:** Discount code detection (found 20FOR200 on The Last Hunt!)
- **NEW:** Real-time code validation

---

## 🐛 Known Issues

> **All 4 issues below were FIXED on 2026-06-17** — see the Session Changelog at the top of this file. Original write-ups kept for reference.
>
> ~~Remaining limitation: The Last Hunt scraper still uses fragile CSS selectors.~~ ✅ Resolved 2026-06-18 — migrated to The Last Hunt's Algolia API (see changelog). Altitude Sports added on the same stack.

### Issue 1: Shoe Size Filtering Limits Search ✅ FIXED
**Problem:** Searching by specific size (e.g., "10.5") is too restrictive  
**Impact:** Scraper misses products even if shoe is in stock  
**Solution Needed:** Remove size field from Shoe model, make size search optional/dynamic

**Current Schema:**
```python
class Shoe:
    brand: str          # Nike
    model: str          # Vaporfly
    size: str           # 10.5 <- PROBLEM: Too specific
    target_price: float
```

**Proposed Schema:**
```python
class Shoe:
    brand: str
    model: str
    # Remove size - search all sizes
    target_price: float
    # Add optional size tracking separately
    preferred_sizes: List[str] = []  # Optional
```

### Issue 2: Target Price Not Filtering After Update ✅ FIXED
**Problem:** Updating target_price in UI doesn't affect scraping results  
**Possible Causes:**
- Frontend not refreshing data after update
- Backend caching target_price
- Deal detection logic using old prices
**Solution Needed:** Verify price update workflow end-to-end

### Issue 3: seed_data.py Not Synced with UI ✅ FIXED
**Problem:** Adding shoes in UI doesn't persist to seed_data.py  
**Current Flow:**
1. User adds shoe via UI → Database updated ✓
2. But seed_data.py file not updated ✗
3. On reset, new shoes are lost

**Solution Needed:** Add script to export database to seed_data.py format

### Issue 4: Scraper Not Finding Boston 13 on JD Sports ✅ FIXED
**Problem:** Product exists (https://jdsports.ca/collections/mens-adidas/products/adidas-adizero-boston-13-black-white-grey-1) but scraper returns no results  
**Possible Causes:**
- CSS selectors need adjustment for JD Sports (different retailer than The Last Hunt)
- Size filtering preventing match
- Search query not matching product name
**Solution Needed:**
- Add JD Sports scraper implementation
- Verify CSS selectors on JD Sports site
- Test with Boston 13 specifically

---

## 📊 Current Database Schema

### shoes Table
```python
id          Integer (PK)
brand       String      # Nike, Adidas, etc.
model       String      # Vaporfly, Adizero Boston 13, etc.
# size REMOVED 2026-06-17 — a model is tracked across ALL sizes
target_price Float      # Price threshold for deals
notes       Text (nullable)
is_active   Boolean     # Track this shoe?
created_at  DateTime
updated_at  DateTime
```

### retailers Table
```python
id                  Integer (PK)
name                String  # The Last Hunt, JD Sports, etc.
base_url            String
scraping_enabled    Boolean
last_scraped_at     DateTime
scraper_config      JSON
created_at          DateTime
updated_at          DateTime
```

### price_records Table
```python
id              Integer (PK)
shoe_id         Integer (FK)
retailer_id     Integer (FK)
product_url     String
price           Float
original_price  Float (nullable)
in_stock        Boolean
size_available  Boolean      # at least one size in stock
image_url       String (nullable)  # NEW (Phase 5): product image CDN URL
colorway        String (nullable)  # NEW (Phase 5): e.g. "Black / White - Grey"
scraped_at      DateTime
```

### deals Table
```python
id                  Integer (PK)
shoe_id             Integer (FK)
retailer_id         Integer (FK)
current_price       Float
target_price        Float
savings_amount      Float
savings_percent     Float
product_url         String
in_stock            Boolean
image_url           String (nullable)  # NEW (Phase 5): product image CDN URL
colorway            String (nullable)  # NEW (Phase 5): colorway name
is_active           Boolean
detected_at         DateTime
discount_codes      String (nullable)  # From code detection
expires_at          DateTime (nullable)
```

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
- `app/models/` - Database models
- `app/scrapers/` - Scraping logic
  - `base_scraper.py` - Framework (HTTP, Playwright, price/promo parsing, Algolia rediscovery)
  - `algolia_scraper.py` - Generic Algolia/commercetools scraper (reusable; auto credential rediscovery)
  - `the_last_hunt.py` - The Last Hunt (extends AlgoliaScraper) ✅
  - `altitude_sports.py` - Altitude Sports (extends AlgoliaScraper) ✅
  - `shopify_scraper.py` - Generic Shopify JSON scraper (reusable; image/colorway/size extraction)
  - `jd_sports.py` - JD Sports Canada (extends ShopifyScraper) ✅
  - `boutique_endurance.py` / `le_coureur.py` / `blacktoe_running.py` / `forerunners.py` - Shopify stores ✅
  - `scraper_manager.py` - Orchestration
- `app/routers/export.py` - Export DB → seed_data.py source

### Frontend (React/Vite)
- `src/pages/`
  - `Dashboard.jsx` - Stats & recent deals
  - `Deals.jsx` - Deal listing
  - `Shoes.jsx` - Shoe management
  - `Retailers.jsx` - Retailer management
  - `PriceHistory.jsx` - Chart view
- `src/components/` - Reusable components
  - `DealCard.jsx`
  - `ShoeForm.jsx`
  - `DiscountCodeBadge.jsx`
  - etc.
- `src/services/api.js` - API wrapper
- `src/lib/utils.js` - Utilities

---

## 🔍 Currently Working Features

### Dashboard
- [x] Total shoes count
- [x] Active deals count
- [x] Best deals list
- [x] Recent deals list
- [x] Scrape button
- [x] Dark mode toggle

### Deals Page
- [x] List all deals
- [x] Filter by brand
- [x] Filter by retailer
- [x] Filter by min savings
- [x] Sort options
- [x] Deal cards with discount codes
- [x] Savings percentage display

### Shoes Page
- [x] Add new shoe
- [x] Edit shoe
- [x] Delete shoe
- [x] View price history
- [x] Dark mode

### Retailers Page
- [x] List retailers
- [x] Add retailer
- [x] Edit retailer
- [x] Enable/disable scraping
- [x] Dark mode

### Code Detection
- [x] Extract codes from HTML
- [x] Found 20FOR200 on The Last Hunt (20% off)
- [x] Validate code format
- [x] Display in deal cards
- [x] Show savings with code applied

---

## 🚀 Running the Project

### Backend
```bash
cd running-shoe-deals/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python seed_data.py
python run.py
```
Runs on: http://localhost:8000

### Frontend
```bash
cd running-shoe-deals/frontend
npm install
npm run dev
```
Runs on: http://localhost:5173

### Both Running
Terminal 1: `python run.py` (backend)
Terminal 2: `npm run dev` (frontend)

---

## 📝 Data Currently in Database

### Retailers (7)
1. The Last Hunt - Has discount code detection working
2. JD Sports Canada - Boston 13 needs scraper work
3. Altitude Sports
4. Sport Experts
5. MEC
6. Running Room
7. Sport Chek

### Shoes (12+)
- Adidas: Adizero Adios Pro 3, Boston 12, SL, **Boston 13** (new)
- Asics: Metaspeed Sky+, Magic Speed 3
- Puma: Deviate Nitro 2, Velocity Nitro 3
- Nike: Vaporfly Next% 3, Alphafly 3, Zoom Fly 5
- Mizuno: Wave Rebellion Pro, Wave Rider 27

### Discount Codes Found
- **The Last Hunt:** 20FOR200 (20% off $200+) ✓ Verified

---

## 🔧 API Endpoints

### Shoes
- `GET /api/shoes` - List all
- `POST /api/shoes` - Create
- `GET /api/shoes/{id}` - Get specific
- `PUT /api/shoes/{id}` - Update
- `DELETE /api/shoes/{id}` - Delete
- `GET /api/shoes/{id}/prices` - Price history

### Retailers
- `GET /api/retailers` - List all
- `POST /api/retailers` - Create
- `GET /api/retailers/{id}` - Get specific
- `PUT /api/retailers/{id}` - Update
- `DELETE /api/retailers/{id}` - Delete

### Deals
- `GET /api/deals` - List all deals
- `GET /api/deals/{id}` - Get specific
- `PUT /api/deals/{id}/deactivate` - Mark inactive
- `GET /api/deals/shoe/{shoe_id}` - By shoe
- `GET /api/deals/retailer/{retailer_id}` - By retailer

### Scraping
- `POST /api/scrape/shoe/{id}` - Scrape one shoe
- `POST /api/scrape/all` - Scrape all shoes
- `POST /api/scrape/retailer/{id}` - Scrape one retailer
- `GET /api/scrape/test/the-last-hunt` - Test The Last Hunt scraper (Algolia)
- `GET /api/scrape/test/altitude-sports` - Test Altitude Sports scraper (Algolia)
- `GET /api/scrape/test/jd-sports` - Test JD Sports scraper (default: Boston 13)

### Export
- `GET /api/export/seed-data` - Current DB rendered as seed_data.py source (text/plain)

### Dashboard
- `GET /api/dashboard/stats` - Statistics
- `GET /api/dashboard/best-deals` - Top deals
- `GET /api/dashboard/recent-deals` - Recent deals

---

## 📦 Dependencies

### Backend
```
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy==2.0.25
playwright==1.41.0
beautifulsoup4==4.12.3
lxml==5.1.0
requests==2.31.0
pydantic==2.5.3
python-dotenv==1.0.0
```

### Frontend
```
react@18
react-dom@18
react-router-dom
@tanstack/react-query
axios
tailwindcss
shadcn/ui
recharts (for price charts)
lucide-react (for icons)
```

---

## 🎯 Phase 4: Automation (Next)

### Features to Add
- [ ] APScheduler for automatic scraping every 6 hours
- [ ] Email notifications for deals
- [ ] More retailer scrapers (JD Sports, Sport Chek, etc.)
- [ ] Price trend analysis
- [ ] Deal expiration tracking
- [ ] Export to CSV

### Bugs to Fix (From This Session)
- [ ] Remove size from shoe model
- [ ] Fix target price filtering
- [ ] Sync seed_data.py with database
- [ ] Add JD Sports scraper
- [ ] Test Boston 13 scraping

---

## 🔗 Useful Links

- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Frontend:** http://localhost:5173
- **Database:** running-shoe-deals/backend/shoe_deals.db

---

## 💡 Key Learnings & Notes

### Working Well ✅
- FastAPI backend is solid
- React frontend responsive and functional
- Dark mode implemented cleanly
- Discount code detection works
- Deal detection logic accurate

### Needs Work 🔧
- Size field too restrictive
- Price filtering not persisting properly
- Scraper needs expansion to more retailers
- seed_data.py sync missing

### Implementation Notes
- CSS selectors vary by retailer (The Last Hunt vs JD Sports)
- Browser automation (Playwright) needed for JS-heavy sites
- Rate limiting essential (2-3s delays)
- Error handling for network issues critical

---

## 🚨 Quick Fixes Needed (Priority Order)

> ✅ Items 1–4 DONE on 2026-06-17 (see Session Changelog). Item 5 (extend code detection) and migrating The Last Hunt off CSS selectors remain.

1. ~~**HIGH:** Remove size field from Shoe model~~ ✅
   - Update database schema
   - Update frontend form
   - Update scraper logic
   - Test with all shoes

2. **HIGH:** Fix target_price filtering
   - Verify API endpoint handles updates
   - Check frontend refresh logic
   - Test deal detection after update

3. **MEDIUM:** Sync seed_data.py with database
   - Create export function
   - Add menu option to export
   - Auto-backup database

4. **MEDIUM:** Add JD Sports scraper
   - Analyze site structure
   - Create new scraper class
   - Test with Boston 13
   - Register in ScraperManager

5. **LOW:** Extend code detection to more retailers
   - Test on Sport Chek
   - Add JS banner parsing
   - Summary on dashboard

---

## 📚 Files to Know

**Critical:**
- `backend/app/models/models.py` - Database schema (size field here)
- `backend/app/scrapers/the_last_hunt.py` - Working scraper example
- `frontend/src/pages/Shoes.jsx` - Shoe form (size field here)
- `frontend/src/services/api.js` - API wrapper
- `seed_data.py` - Need to sync with database

**Important:**
- `backend/app/main.py` - FastAPI setup
- `frontend/src/pages/Dashboard.jsx` - Main view
- `backend/app/models/schemas.py` - API schemas
- `frontend/src/pages/Deals.jsx` - Deal listing

---

## 🎓 Technical Details

### Size Field Issue Deep Dive
Current:
```python
shoe = Shoe(brand="Adidas", model="Boston 13", size="10.5")
# Scraper looks for size 10.5 specifically
# Misses size 10 or 11 even if same model
```

Better:
```python
shoe = Shoe(brand="Adidas", model="Boston 13")
# Scraper finds all sizes
# Optional: User selects sizes they want post-search
```

### Price Filter Issue Deep Dive
Steps to debug:
1. Update shoe target_price via API (`PUT /api/shoes/{id}`)
2. Verify database was updated (`SELECT * FROM shoes WHERE id=?`)
3. Trigger scrape (`POST /api/scrape/shoe/{id}`)
4. Check if deals created with new price threshold
5. If not, check deal creation logic in `scraper_manager.py`

---

## ✨ Recent Achievements

- ✅ Built complete React frontend
- ✅ Implemented dark mode
- ✅ Added discount code detection
- ✅ Found real discount code (20FOR200)
- ✅ Tested and verified all working at localhost:5173
- ✅ Integrated frontend with backend API

---

**Note:** This file should be updated after each development session with new findings, bugs, and completed tasks.
