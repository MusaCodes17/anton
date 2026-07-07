# Anton — Dead Code Analysis (Prompt 7)

**Companions:** `refactoring/refactor.md` (Prompt 6 — several entries cross-reference its findings), `docs/architecture.md`, `docs/dependency_graph.md`, `docs/design_decisions.md` (verdicts A6/C6/D7/E2/E5 govern several "dormant, keep" calls below), `docs/project_state.md` §6/§7.
**Generated:** 2026-07-05, against the post-Phase-5 tree (`models.py` 18,151 bytes; changelog top entry = 2026-07-04 canonical activities). **Nothing was deleted** — this is an inventory.

**Method & coverage.** Backend: every router, service, scraper, model/schema file, `main.py`, `scrape_runner`, `coros_client`, `mcp_server.py`, the test suite, and the repo/backend root were read; "unused route" claims are checked against the complete frontend API client (`services/api.js`), every hook in `useApi.js`, and every consumer of those hooks. Frontend: **all 10 pages, all 22 root components, both chat components, `Layout`, all 5 `lib/` modules, and both custom hooks were read in full** — component/API usage claims below rest on that complete read, with two stated gaps: the four `components/training/*` files and the `components/ui/` shadcn primitives were not read (the training components receive data via props/race-hooks from `Training.jsx` and would not plausibly consume the deal/dashboard APIs at issue; the ui primitives are generic and out of scope). No grep tool was available on this machine, so "nothing references X" means "nothing in the files read references X" — each entry names what to double-check before deleting.

**Confidence scale:** High = every plausible consumer was read and none references it · Medium = strong evidence with a named residual unknown · Low = suspicion only.
**"Safe to delete"** always assumes: on a clean working tree, one commit per cluster, suite green after (the bar is the live count in `docs/changelog.md`'s newest entry — 64 as of 2026-07-06), and the standing rule that **dormant-by-decision code (C6 etc.) is not dead code** — those entries are explicitly marked *keep*.

---

## 1. Definitely unused files

### 1.1 `backend/test_scraper.py` (repo `backend/` root)
**What it is:** an interactive standalone script ("Press Enter to start live scraping test…") exercising `TheLastHuntScraper` with hard-coded queries, written for the CSS-selector era of that scraper.
**Why it appears unused:** nothing imports it; it isn't a pytest module (top-level `input()` would hang collection if it were); its purpose is fully superseded twice over — by the `GET /scrape/test/*` endpoints (themselves legacy, §5.1) and by the universal `POST /shoes/test` dry-run + `ScrapabilityTestModal` UI. The `scraper_manager.py` shim docstring still lists it as an importer, which is itself stale: the script imports `the_last_hunt` directly, not the shim.
**Confidence:** High. **Safe to delete:** yes. **Check first:** update the shim's docstring importer list in the same commit (or it will name a ghost).

### 1.2 `backend/view_db.py`
**What it is:** a `sqlite3` + `tabulate` console dumper of shoes/retailers/prices/deals.
**Why it appears unused:** nothing imports it; it predates the entire rotation/training domain (it knows none of the 2026 tables) and is superseded by the web UI, the MCP resources, and any SQLite browser. It is also the **only** consumer of the `tabulate` dependency found anywhere.
**Confidence:** High. **Safe to delete:** yes. **Check first:** delete `tabulate==0.9.0` from `requirements.txt` in the same commit (§8.2) — and only then.

### 1.3 `frontend/src/components/StatCard.jsx`
**What it is:** the "Velocity"-style metric tile from the removed Dashboard page.
**Why it appears unused:** the old Dashboard was deleted 2026-07-03 (project_state §9.4); all 10 pages and all other components were read and none imports it. Tellingly, four surfaces now implement their *own* local stat tile instead (§4.4).
**Confidence:** High (residual unknown: the unread `training/` components — but `Training.jsx` defines its own local `Stat`, so they demonstrably don't standardize on StatCard either). **Safe to delete:** yes. **Check first:** a project-wide search for `StatCard` (the one true grep this analysis couldn't run).

### 1.4 `.DS_Store` files (`backend/`, `backend/app/`, `backend/app/services/`) and `.playwright-mcp/` session artifacts
**Why unused:** macOS Finder droppings and browser-testing session logs/snapshots — not code at all.
**Confidence:** High. **Safe to delete:** yes. **Check first:** that `.gitignore` covers both patterns so they don't return; nothing else.

---

## 2. Probably unused files

### 2.1 Superseded DB backups in `backend/` (four of five)
`shoe_deals.db.bak` (188 KB), `.bak_pre_dealfix` (392 KB), `.bak_pre_variantfix` (464 KB), `.bak-strava` (6.2 MB) — restore points for changes long since verified in production use. **`shoe_deals.db.bak-pre-activities` (10.5 MB) is NOT in this list**: it is one day old and is the designated restore point for the deepest migration ever run here; keep it until the canonical-activities change has aged several weeks of daily use.
**Why they appear unused:** each protected a specific change whose success has since been proven by weeks of live operation; none is restorable *forward* anyway (their schemas predate later migrations — restoring one means replaying Alembic).
**Confidence:** High that they're never restored; the *decision* is a data-retention call, not a code call. **Safe to delete:** the four old ones, probably — but the better move is design_decisions E2 🕐 / architecture §16.2 as written: relocate all backups out of the tree with a dated naming convention, in one pass, rather than piecemeal deletion. **Check first:** `git ls-files` — if any `.bak*` is actually tracked in git history it's worth knowing before adding ignore rules; and confirm `.gitignore` covers `*.bak*` going forward.

### 2.2 `backend/legacy_migrations/` (9 scripts + README)
**Why it appears unused:** pre-Alembic idempotent `ALTER TABLE` scripts; the live DB is far past all of them, Alembic's baseline supersedes them for fresh DBs, and nothing imports them.
**Confidence:** High that they never execute again. **Safe to delete:** *deliberately deferred* — design_decisions A6 ⚠️ already schedules "archive `legacy_migrations/`" as part of resolving schema authority. Do it there, as one decision, not as a drive-by. **Check first:** nothing technical; just pair it with the A6 sweep so the design-decision entry flips to Superseded correctly.

---

## 3. Legacy experiments

### 3.1 The CSS-selector scraping era, surviving as comments and defaults
`Retailer.scraper_config`'s model comment still says it stores "CSS selectors, patterns" — no current scraper reads selectors from config (Algolia reads credentials; Shopify/EnRoute read nothing but `use_browser`). Harmless, but it documents an architecture that no longer exists.
**Confidence:** High (all scraper files read). **Safe to delete:** the comment text, yes — one-line docs fix, not a schema change. **Check first:** nothing.

### 3.2 `backend/test_scraper.py`
Also belongs here (the "old CSS-selector approach found nothing" era) — inventoried at §1.1.

### 3.3 Drawer-only chat conversations
Not dead code — but `ChatDrawer` deliberately runs an *unpersisted* `useChatStream` (fresh on every mount, hand-off to the full page via `sessionStorage`). Recorded here only so a future session doesn't "fix" the drawer's lack of persistence as if it were a bug; it's a design choice adjacent to C8 ⚠️.

---

## 4. Duplicate implementations

*(The big ones — MCP dict serializers vs Pydantic, pace formatting ×3, provider loop ×3, shoe-type vocabulary ×4 — are already ranked in `refactor.md` H5/M2 and `dependency_graph.md` §9. Listed here are the duplicates this pass found that aren't yet on any ledger.)*

### 4.1 COROS shoe-suggestion heuristic, implemented twice with different rules
The `sync_coros_runs` MCP prompt encodes the canonical pace-primary/distance-secondary suggestion tables; `CorosSyncModal.jsx` (`suggestShoe`) implements its **own, simpler** heuristic (single 4:10/km race-pace threshold, substring matching on type names). Two suggestion engines, different answers for the same run.
**Confidence:** High. **Safe to delete:** neither yet — the modal fronts the dormant server path (C6 🕐); if that path ever revives, reconcile the heuristics (ideally by serving suggestions from the backend so both AI and UI use one rule). Until then this is a keep-with-asterisk.

### 4.2 Local stat-tile components, four times
`Stat` in `Training.jsx`, `Stat` in `ShoeDetail.jsx`, `StatRow` in `SettingsSync.jsx`, `StatusTile` in `Retailers.jsx` — plus the orphaned `StatCard.jsx` (§1.3) none of them uses. Page-local sub-components are the stated convention (CLAUDE.md §3), so this is only *worth acting on* when one of them next changes; delete `StatCard` regardless.

### 4.3 Relative-time formatting, twice
`lib/utils.formatRelativeTime` and a private `formatRelativeTime` inside `ChatPage.jsx` (slightly different buckets). One import would do. **Confidence:** High. Trivial.

### 4.4 `GET /retailers/{id}/promos` vs `Retailer.active_promo_codes`
The dedicated promos endpoint and the property embedded in every retailer response answer the same question; the frontend exclusively uses the embedded property (`PromoManagerDialog` reads `retailer.active_promo_codes`). One of the two is redundant — see §5.4 for the recommendation.

### 4.5 `models/__init__.py` vs `scrapers/__init__.py` package façades
Both re-export aggregations that have drifted: the models façade is missing the entire `Activity`-era additions (`PlannedRace`, `StravaGearMapping`, every race/strava schema, `PlannedShoeBrief`, `LastSeenPrice`…) while still exporting schemas nothing uses (§6.2); the scrapers façade exports `TheLastHuntScraper` and the shim's `ScraperManager` for consumers that all import concretely. Already flagged as import-style debt in dependency_graph §11.4 — inventoried here because *stale façades are how dead exports hide*. **Safe to delete:** don't delete the packages; either complete the façades or empty them, per §11.4's either/or.

---

## 5. Unused API routes

Claims below are grounded in the complete `api.js` + hook-consumer read; the MCP server calls services/ORM directly (never REST), and Claude Desktop speaks MCP — so "no frontend caller" means "no known caller at all" for this single-user system. Residual unknown for every entry: ad-hoc curl/bookmark usage only the runner can rule out.

### 5.1 `GET /scrape/test/the-last-hunt`, `/scrape/test/altitude-sports`, `/scrape/test/jd-sports`
**Why unused:** no `api.js` function exists for them; fully superseded by `POST /shoes/test` (all retailers, same no-DB dry-run, with a real UI). Already sentenced in project_state §6.6 ("candidates for removal, not repair") and dependency_graph §11.11.
**Confidence:** High. **Safe to delete:** yes — and deleting them also removes three of the function-level imports flagged in dep_graph §8.7. **Check first:** nothing beyond the runner's own muscle memory.

### 5.2 `POST /admin/cleanup-kids-shoes` (and with it, all of `routers/admin.py`)
**Why unused:** self-described one-off ("Run once after deploying that filter"); the filter deployed in June; no frontend caller; the router contains nothing else.
**Confidence:** High that nothing calls it; Medium that its job is fully done (can't verify from code that it was ever run). **Safe to delete:** yes, with a ritual: run it once more first — it no-ops when clean and reports counts, which is its own proof. **Check first:** that one final invocation; then remove the router, its `main.py` include, and note that this deletes the only consumer of `BaseScraper.is_kids_shoe` *outside* the scrape path (the scrape-path usage remains, so the method stays).

### 5.3 `GET /dashboard/recent-deals` and `GET /dashboard/best-deals`
**Why unused:** their only consumer was the Dashboard page removed 2026-07-03; `dashboardApi.recentDeals`/`bestDeals` client functions survive but nothing calls them (§7.1); Home's top-deals module uses `/api/home`. `GET /dashboard/stats` is **not** unused (Layout sidebar + SettingsSync) — keep it.
**Confidence:** High. **Safe to delete:** yes — endpoints and client functions together. **Check first:** nothing found; the `useDashboardStats` hook and `/stats` stay.

### 5.4 `GET /retailers/{id}` and `GET /retailers/{id}/promos`
**Why unused:** `retailersApi.get` and `retailersApi.promos` have no callers; the UI reads promos via the embedded `active_promo_codes` property (§4.4) and never fetches a single retailer.
**Confidence:** High for current usage; Medium as a deletion recommendation, because get-by-id is cheap REST completeness. **Safe to delete:** the promos endpoint yes (it's a duplicate read path); get-by-id is a judgment call — delete or keep, but delete the orphaned client functions either way. **Check first:** nothing.

### 5.5 `GET /shoes/{shoe_id}` and `GET /deals/{deal_id}`, `GET /deals/shoe/{shoe_id}`, `GET /deals/retailer/{retailer_id}`
**Why unused:** `shoesApi.get`, `dealsApi.get`, `dealsApi.forShoe`, `dealsApi.forRetailer` exist but no page or component calls them (the deep-link modal finds its deal inside the already-fetched list; replacement deals use their own owned-shoes endpoint; MCP has native `get_shoe_deals`).
**Confidence:** High for current usage. **Safe to delete:** the three deal sub-routes yes; the two get-by-ids are the same REST-completeness judgment as §5.4. Note deleting `GET /shoes/{shoe_id}` also removes the route-ordering trap where `/shoes/summary` and `/shoes/test` must stay declared above the catch-all `/{shoe_id}`. **Check first:** whether Son of Anton conversations have ever been pointed at raw REST URLs (they use MCP tools, so no — but it's the one imaginable caller).

**Not unused, for the record:** everything else — including `GET /export/seed-data` (Shoes page export button), `GET /shoes/summary` (Shoes page fallback prices — a genuinely nice windowed query), all `/owned-shoes/*`, `/watchlist`, `/activities`, `/training/*`, `/races`, `/home`, `/strava/status`, all `/chat/*` (providers/resources/resource-read/message all have live consumers), and the whole COROS sync trio (dormant-gated but UI-wired, §9.1).

---

## 6. Unused models

### 6.1 `Deal.expires_at` column
**Why it appears unused:** nothing ever writes it — not `DealStore.upsert_deal`, not the orchestrator, not any router — so it is NULL on every row; it's exposed in `DealResponse` as permanent `null`.
**Confidence:** High (all Deal writers read). **Safe to delete:** yes, as part of the next Alembic migration touching `deals` (never worth its own migration); drop it from the schema class at the same time. **Check first:** a `SELECT COUNT(*) FROM deals WHERE expires_at IS NOT NULL` against the live DB for the definitive answer.

### 6.2 Unused Pydantic schemas (schemas.py)
`PriceRecordCreate`, `PriceRecordResponse`, `DealCreate`, `ScrapeRequest`, `ScrapeResult` — none appears in any endpoint signature or construction site. `DealStore` builds ORM objects directly; `/shoes/{id}/prices` and MCP price history return hand-shaped dicts; `scraping.py` **imports** `ScrapeRequest`/`ScrapeResult` and then never references either name (a two-line unused import). The stranded-`HttpUrl` import and the legacy `size_available` field are already in refactor.md M1 — cited, not restated.
**Confidence:** High. **Safe to delete:** yes — schemas, the scraping.py import line, and their entries in the `models/__init__` façade together (§4.5). **Check first:** that no *test* constructs them (the read test modules don't; `test_watchlist` defines its own local response models).

### 6.3 Dormant reference data — **keep** (classification, not deletion)
`StravaGearMapping` model, `services/strava_gear.py`, `scripts/seed_gear_mappings.py`: dormant since the backfill retired, retained deliberately as the record of human mapping decisions and for any future re-import (architecture §7, domain_model §2.2). **Not dead code.** Same for `scripts/import_strava.py` (re-import is a supported operation).

---

## 7. Unused utilities

### 7.1 Frontend API-client functions with no callers
`dealsApi.get` · `dealsApi.forShoe` · `dealsApi.forRetailer` · `dashboardApi.recentDeals` · `dashboardApi.bestDeals` · `retailersApi.get` · `retailersApi.promos` · `shoesApi.get`.
**Why unused:** complete read of every page/component/hook found zero call sites; they mirror the unused routes in §5.
**Confidence:** High (with the training-components caveat from the header — they receive data via props and the race hooks, none of which route through these). **Safe to delete:** yes, in the same commit as their §5 endpoints so client and server stay mirrored. **Check first:** nothing further.

### 7.2 `queryKeys.shoe(id)` in `useApi.js`
A `['shoes', 'detail', id]` key factory with no corresponding hook (there is no `useShoe`) and no invalidation targeting it. **Confidence:** High. **Safe to delete:** yes — one line.

### 7.3 `BaseScraper.is_in_stock(html, soup)`
**Why it appears unused:** every live scraper derives stock structurally — Algolia from `quantity_left`, Shopify from variant `available`, En Route from `availableForSale`. No subclass or orchestrator call site references it. Its one *cousin* consumer, `admin.py`'s use of `is_kids_shoe`, is a different method (and itself slated in §5.2).
**Confidence:** High (all scraper files read in full). **Safe to delete:** yes. **Check first:** nothing — but note it's the kind of method a future bespoke HTML scraper might have wanted; deleting is still right (it was a blunt whole-page phrase match; a future scraper deserves better).

### 7.4 `Retailer` promos duplicate-read utility — see §4.4/§5.4.

---

## 8. Unused dependencies (obsolete `requirements.txt` entries)

The requirements file is where dead code hides longest. Findings, each with its evidence and check:

| Package | Verdict | Evidence / check before removing |
|---|---|---|
| `apscheduler==3.10.4` | **Unused — decision already open** | E5 ⚠️: no scheduler wired anywhere; remove *or* design scheduled scraping — don't leave it inviting drive-by wiring. Cited, not new. |
| `fastapi-cors==0.0.6` | **Almost certainly unused** | CORS comes from FastAPI's built-in `fastapi.middleware.cors` (main.py); the third-party `fastapi-cors` package is a different, unimported thing. Check: `pip show`/import search, then drop. |
| `tabulate==0.9.0` | **Unused once §1.2 lands** | Only consumer is `view_db.py`. Delete together. |
| `pydantic-settings==2.1.0` | **Probably unused** | No `BaseSettings` anywhere read; config is raw `os.getenv` throughout. Check: repo-wide import search. |
| `python-multipart==0.0.6` | **Probably unused** | Needed only for `Form`/`File` endpoints; none exist. Check: FastAPI will raise at startup on a form endpoint without it, so removal is self-verifying — run the suite + boot. |
| `html5lib==1.1` | **Probably unused** | Every `BeautifulSoup(...)` call read uses the `lxml` parser. Check: search for `"html5lib"` string before dropping. |
| `pytz==2024.1` | **Probably unused directly** | The codebase standardized on `zoneinfo` (B14); pandas bundles its own tz handling. Check: `strava_import.py` (not re-read this pass) for a direct `import pytz` before dropping. |
| `python-dateutil==2.8.2` | **Keep** | pandas requires it transitively regardless; pinning it explicitly is harmless. |

**Confidence:** per-row above. **Safe to delete:** only after the named check per row, one commit, suite green + app boot + one manual scrape.

---

## 9. Obsolete scripts

### 9.1 Server-side COROS sync stack — **dormant by decision, keep** (the important non-deletion)
`coros_client.py`, `services/coros.py`, `routers/coros_sync.py`, MCP `get_coros_sync_status`/`fetch_unsynced_coros_runs`/`confirm_coros_run`, and the whole frontend surface (`CorosSyncModal`, `useFetchCorosRuns`/`useConfirmCorosRuns`, the My-Shoes "Sync from COROS" button that self-disables when unconfigured). C6 🕐 governs: this revives if COROS ever opens API access; deleting it would be re-writing it later.
Two caveats recorded so revival doesn't trip on them: **(a)** `coros_client.activity_to_run_dict` derives the run date via `datetime.fromtimestamp(ts, tz=timezone.utc)` — a **UTC date**, which violates the America/Toronto calendar rule (B14) and would shift evening runs a day if this path ever went live; **(b)** `confirm_coros_run` (the MCP tool) is *not* env-gated and works today — refactor.md M5's prompt-vs-practice reconciliation applies before trusting either caveat's operational status.
**Confidence in "dormant, not dead":** High. **Safe to delete:** no.

### 9.2 `scripts/seed_gear_mappings.py` — dormant reference, keep (§6.3).
### 9.3 `test_scraper.py`, `view_db.py` — the actual obsolete scripts; inventoried at §1.1/§1.2.
### 9.4 `seed_data.py` — **live**, not obsolete: it's the code-as-backup target of `GET /export/seed-data` (E2), regenerated from the UI's Export button. Listed to disambiguate.

---

## 10. Unreachable code

### 10.1 `BaseScraper._fetch_with_browser` (the Playwright page-fetch path)
**Why unreachable today:** it runs only when `fetch_page(use_browser=True)`, which happens only when a scraper's `config["use_browser"]` is truthy — and every constructor read (all eight bespoke, both platform bases, both dynamic builders) hard-codes `use_browser: False`. The only Playwright that actually runs is `discover_algolia_credentials`, which drives its own browser directly.
**Confidence:** High for current configs; Medium overall, because a DB `scraper_config` row could flip the flag without any code change — it's *config-reachable*, not *code-reachable*.
**Safe to delete:** defensible but not recommended — it's the designated escape hatch for a future JS-heavy retailer, small, and tested by existence in the base contract. Recommended action instead: a one-line comment marking it currently config-dormant, so the next reader doesn't assume it's exercised. **Check first (if deleting):** `SELECT scraper_config FROM retailers` for any `use_browser: true`.

### 10.2 `AlgoliaScraper` unused constructor knob
`search_selector` defaults to `[data-testid="global-search-input"]` and `homepage_url` to `base_url`; no subclass or dynamic builder overrides either. Reachable (rediscovery uses them) — listed only because the parameters *look* like live variation points and are actually constants. Not actionable beyond a comment.

### 10.3 The `for/else` clauses in `chat_service` provider loops
Reachable by design (the MAX_AGENTIC_TURNS exhaustion path) — explicitly *not* dead; noted because `for/else` is rare enough that a cleanup pass might misjudge it. The inline comments already defend it.

---

## Suggested execution order (one cleanup session)

1. **Zero-risk deletions, one commit:** `test_scraper.py`, `view_db.py` (+ `tabulate`), `StatCard.jsx`, `queryKeys.shoe`, the eight orphaned `api.js` functions, the `ScrapeRequest`/`ScrapeResult` import line, `.DS_Store`s (+ gitignore).
2. **Route removals, one commit each cluster:** the three `/scrape/test/*` endpoints; `admin.py` (after one final no-op run); the two dashboard deal endpoints; the deal/retailer/shoe sub-routes per the §5.4/§5.5 judgment calls.
3. **Schema tidy, riding the next migration:** drop `Deal.expires_at` + the unused Pydantic schemas + façade updates (pairs naturally with refactor.md M1's `size_available` deprecation).
4. **Dependency prune, one commit, checks per §8 table.**
5. **Deferred to their governing decisions:** `legacy_migrations/` and `.bak` relocation → A6/E2 sweep; `scraper_manager` shim → dep_graph §11.2 (it is *transition scaffolding with four live consumers*, never dead code); everything in §9.1/§6.3 stays.

Expected suite impact: zero (nothing inventoried above has tests, which for §5's routes is itself refactor.md H1's point).

---

*Maintenance note: strike entries here with a changelog pointer as they're executed. If a "probably" entry turns out to have a caller this analysis missed, don't just skip it — record the caller here, because an undiscoverable consumer is its own finding. Re-verify §5 and §7 after any new page ships; the fastest way dead code returns is a mirrored client function for an endpoint that never got a UI.*
