# MAINTENANCE_PLAN.md — Post-R4 Defects, Debt & Housekeeping

**Written:** 2026-07-13 (full-repo review session; Claude web). **Updated:** 2026-07-14 — D7/D8 scraper defects added from live UI observation; I1 New-Retailer Onboarding Agent added; RA1.5 explicitly deferred pending the hosting decision (Fly.io vs Hetzner, D0), defects block now leads.
**Status:** executing contract for the next several sessions. **RA1.5 is deferred by decision (2026-07-14)** until the hosting choice is made; §0 stays in the plan untouched as the parked queue.
**Sources reconciled:** `docs/project_state.md` (2026-07-10 snapshot), `refactoring/tech_debt.md` ledger, `refactoring/refactor.md`, `docs/roadmap.md`, root-doc inventory, `.gitignore`.
**Conventions:** one commit per lettered task, `mx:` prefix (maintenance), suite green each session, backend-with-tests before UI, E4 bar on any migration.

---

## 0. Urgent — do these first (human, not Claude Code)

| # | Action | Detail |
|---|---|---|
| U1 | **Execute RA1.5 cutover** | Everything else in this plan is secondary. Provision the VM (Fly.io / Hetzner CX22 per D0), DNS, fill `deploy/.env.production`, deploy, E4 count reconciliation (933+ activities), re-point Claude Desktop, add the claude.ai connector. Runbook: `REMOTE_ACCESS_PLAN.md` §6/§7. |
| U2 | **RA1.4 human steps (at/with U1)** | Provision Backblaze B2 bucket + `LITESTREAM_*` vars; run the restore drill (`deploy/restore.sh` to a scratch path, verify activity count); pull laptop snapshot post-cutover (`deploy/pull-snapshot.sh`). |
| U3 | **RA1.3 human step** | External uptime pinger on `/health` before cutover completes. |
| U4 | **RA1.6 docs reconciliation** | After cutover: `architecture.md` §11 internet trust model; A1 amended; E9 finalized; `CLAUDE_DESKTOP_SETUP.md` remote URL. (Claude Code session, but gated on U1.) |

---

## 1. Defects (open, verified against the ledger 2026-07-13)

Ordered by risk to live data / feed honesty.

| # | Defect | Source | Fix sketch | Effort |
|---|---|---|---|---|
| D1 | ✅ **Done 2026-07-14** — `database.py` now registers a SQLAlchemy event listener that sets `PRAGMA foreign_keys=ON` on every SQLite connection. `rotation.delete_owned_shoe()` added: NULLs `PlannedRace.planned_shoe_id` and `StravaGearMapping.owned_shoe_id` (nullable FKs); deletes `CheckpointPrompt` records (NOT NULL FK); preserves strava archive activities (INV-4); ORM cascade handles ShoeRun + ShoeNote. `DELETE /owned-shoes/{id}` updated to call the sanctioned path. `PRAGMA foreign_key_check` run against live DB beforehand — no violations. 10 new tests in `test_delete_owned_shoe.py`. | tech_debt P1-3 / §11.4; refactor.md H3 | ✅ Fixed | — |
| D2 | ✅ **Done 2026-07-08 (bcdddc2)** — `scrape_retailer_for_shoe` tracks `searched_urls` (every URL returned by search) alongside `fetched_urls` (successful detail fetches) and orphan-retires against their union. `test_partial_detail_failure_does_not_orphan_a_live_deal` is a real pass (was never truly xfail after the fix). No code change needed in this session; stale module comment in `test_orchestrator.py` updated. | tech_debt P1-2 / §11.3; refactor.md H2 | ✅ Fixed | — |
| D3 | ✅ **Done 2026-07-14** — live DB verified: all 13 COROS activities carry `coros_activity_id`; dedup primary tier is working. Fallback (date + ±0.1 km) is backup only; no code fix needed. Also fixed `is_already_logged` to use `date.fromisoformat(act_date)` instead of raw ISO string comparison (D4b — correct on non-SQLite backends). | tech_debt §11.6; refactor.md M5 | ✅ Verified + D4b fixed | — |
| D4 | ✅ **Done 2026-07-14** — (a) `trigger_scrape` dict-iteration bug fixed: reads `results.get("deals_found", 0)` / `results.get("total_deals_found", 0)` directly; (b) `is_already_logged` uses `date.fromisoformat(act_date)` (folded into D3 above); (c) `active_promo_codes` sort key changed from `or 0` to `or datetime.min` to fix TypeError on uncommitted row; (d) brand case-sensitivity: already fixed in service extraction (`Shoe.brand.ilike`), no action needed. | tech_debt §11.14; refactor.md L1/L5/L4e | ✅ Fixed | — |
| D5 | ✅ **Done 2026-07-14** — `Deals.jsx` code read confirms no sparkline exists. `project_state.md §4` updated to "confirmed not built". Consider as I3 improvement. | project_state §4 | ✅ Confirmed | — |
| D6 | ✅ **Done 2026-07-14** — `test_get_status_disabled_by_default` now also `monkeypatch.delenv("SCRAPE_SCHEDULE_CRON", raising=False)`. Suite restored to all-green. | project_state §2 | ✅ Fixed | — |
| D7 | ✅ **Done 2026-07-14** — (a) `is_kids_shoe` extended to variadic `*texts`; `search_products_filtered` now passes name + product_url; (b) `_is_youth_size(label)` added to `ShopifyScraper`; variant loop restructured to read label first and skip Y/C-suffix variants before adding to price pool or `sizes_available`. 26 tests in `test_kids_filter.py`. Note: configurable adult size floor (US 7) deferred — Y/C suffix detection handles the egregious JD Sports cases; a floor adds complexity for little gain given the name/URL filter. | UI observation (Musa, 2026-07-14) + code read | ✅ Fixed | — |
| D8 | ✅ **Done 2026-07-14** — orchestrator `scrape_retailer_for_shoe` now requires `below_msrp AND is_stocked`; OOS products retire any active deal (requalifies on next scrape). Shopify `available` default flipped to `False`. `ShoeProductCard` already showed "Out of stock" badge (belt-and-braces confirmed already in place). 3 new tests in `test_orchestrator.py`. | UI observation (Musa, 2026-07-14) + code read | ✅ Fixed | — |

---

## 2. Tech debt (open P1s and worth-doing P2s)

| # | Item | Source | Direction | Effort |
|---|---|---|---|---|
| T1 | **`mcp_server.py` god object** — ~22 tools + 10 resources + prompts + hand-rolled serializers + embedded business rules (600/700/800 km messages, review template) REST can't see. | P1-6 | Extract serializers to a `services/serializers.py` (pairs with T2); move threshold/review copy into `rotation`; split tool registration by domain module. | High (own session) |
| T2 | **Dual serialization** — Pydantic REST vs `_*_to_dict` MCP; owned-shoe shape exists in ≥3 hand-synced renderings. The standing source of the next "numbers disagree" bug. | P1-7 | Single serializer layer both surfaces call. Do with/after T1. | High |
| T3 | ✅ **Done 2026-07-14** — `OWNED_SHOE_STATUSES` tuple + `validate_owned_shoe_status` on `OwnedShoeCreate`/`OwnedShoeUpdate` (off-vocab → 422; read schemas unvalidated). Live values (active/retired) already in-vocab — no sweep. 4 tests. | P1-5 / M2 | ✅ Fixed | — |
| T4 | ✅ **Done 2026-07-14** — `tests/test_migrations.py`: subprocess `alembic upgrade head` against a fresh tmp SQLite DB, asserts load-bearing tables exist (production boot path now covered). | §8.3 | ✅ Fixed | — |
| T5 | ✅ **Already done — verified 2026-07-14.** The listed gaps were closed by `test_deal_store.py` (commit `5cb5c56`, **2026-07-08** — 5 days before this plan was written; the plan missed it): retirement, requalification, all three orphan-guard cases, promo manual-beats-scraped. `test_orchestrator.py` adds the MSRP truth table + D2 partial-detail guard + D8 OOS retire/requalify. **Extended today (T5):** 2 orchestrator tests — target-ignored-in-qualification (INV-6) + price-requalify round-trip. Residual is HTTP-layer endpoint tests (§8.2, separate item). | P1-4 / §8.1 | ✅ Covered (+2) | — |
| T6 | ✅ **Done 2026-07-14** — added `PlannedRace`, `StravaGearMapping`, `AthleteMetric`, `OAuthAuthCode`, `OAuthToken` to the façade import + `__all__`. (Unused-schema removal deferred — low value, risks façade consumers.) | §9.1 | ✅ Fixed | — |
| T7 | ✅ **Done 2026-07-14 (comment)** — `scraper_config` comment rewritten (Algolia-credentials-only; CSS-selector era gone). TypedDict/Pydantic shaping of the JSON blob deferred (low value; a JSON column with one populated shape). | §10.2 | ✅ Comment fixed; typing deferred | — |
| T8 | ✅ **Done 2026-07-14** — struck all rows resolved since generation (P1-3/D1, P1-5-status/T3, P1-9/R2.2, P1-10+§6.1/router extractions, §8.3/T4, §9.1/T6, §9.2/CLAUDE §14); narrowed P1-4, §2.1; suite count 64 → 371; dated re-stamp added. | this review | ✅ Fixed | — |
| T9 | ✅ **Done 2026-07-14** — `.pytest_cache/` and `.venv/` added to root `.gitignore`. | this review | ✅ Fixed | — |
| T10 | **ShoeRun proxy trap (residual)** — all five current seams eager-load (R1.4), but the N+1/`filter()` trap remains armed for any *new* run-list code. | P1-1 | No action now; kept on the ledger. Optional: refactor.md H4's `contains_eager` helper to make the safe path the easy path. | — |

---

## 2.5 New improvements (added 2026-07-14)

| # | Item | Detail | Effort |
|---|---|---|---|
| I1 | **New-Retailer Onboarding Agent** (roadmap candidate **R4.6**). When a retailer is added (via Settings → Retailers or MCP) without a working scraper, an agent workflow takes it from "row in the DB" to "scraping or honestly declared unscrapable": (1) detect retailers with no successful `scrape_runs` entry and no/empty `scraper_config`; (2) run the existing `platform_detection` (Shopify/Algolia sniff) against the base URL; (3) run the scrapability dry-run (`POST /shoes/test` path) with a known shoe; (4) report findings + proposed `scraper_config` via a new `onboard_retailer` MCP tool + `retailer_onboarding` prompt — **C9 confirmation gate before any config write**; unscrapable outcomes get recorded on the retailer row (the Sporting Life precedent) so the watchdog doesn't nag. Builds entirely on existing pieces (`platform_detection.py`, dry-run endpoint, `scrape_health`); the agent is mostly orchestration + one write path. Surfaces in `scrape_health` as a `needs_onboarding` list so the R4.2 Scrape-Reliability watchdog and this share one health view. | Medium |

---

## 3. Housekeeping (docs & repo hygiene)

| # | Item | Detail |
|---|---|---|
| H1 | ✅ **Done 2026-07-13** — `TROUBLESHOOTING.md` + `QUICKSTART.md` archived to `docs/archive/` (actively wrong: pre-Alembic, `seed_data.py`/`run.py` era, delete-the-DB advice). See `docs/archive/README.md`. Commit the move. |
| H2 | ✅ **Done 2026-07-14** — all 9 completed plans `git mv`-ed to `docs/archive/`. Cross-reference sweep updated every path citation in the living docs (architecture tree + threat-model pointer, ai_context tree + orientation, CLAUDE.md §3, design_decisions E1/E7, roadmap R2.7/R5.6, project_state, `.claude/skills/add-frontend-page`, `.claude/commands/phase`, `REMOTE_ACCESS_PLAN`, `docs/archive/README`). **Deliberately not rewritten** (CLAUDE.md §13, append-only history): `docs/changelog.md` session entries and the dated `docs/documentation_review.md` — those are names, not live navigation. Kept at root: `CLAUDE.md`, `REMOTE_ACCESS_PLAN.md`, `CLAUDE_DESKTOP_SETUP.md`, this file. Sweep verified clean; no code references the moved files; suite 372. |
| H3 | ✅ **Done 2026-07-14 (with R1)** — chat `SYSTEM_PROMPT` now says "built into Anton (the user's personal running platform)". The one user-visible pre-brand string is fixed (tech_debt §2.4 / refactor.md L4b struck). |
| H4 | **Stray root artifacts** — `training-default.png` (gitignored scratch screenshot) and `.DS_Store` files: delete locally at will; nothing to commit. |

---

## 4. Rename: `running-shoe-deals` → `anton` (supersedes E6's "keep for now")

E6 deliberately deferred this; the RA milestone makes now the right moment — do it **before** RA1.5 so the deployed host, image names, and connector URL are born with the final name, or immediately **after** cutover as one atomic pass. Do not do it mid-cutover.

**R1 — In-repo strings ✅ Done 2026-07-14:**
- Flipped: FastAPI `title` + root message + `description` (`main.py`), chat `SYSTEM_PROMPT` (H3), COROS-sync agent prompt (`mcp_server.py`), `FastMCP("anton")` server name, platform-probe User-Agent, `backend/README.md` + `frontend/README.md` headers, `frontend/package.json` + `package-lock.json` `name` (→ `anton-frontend`), and the `run.py`/`view_db.py`/`test_scraper.py` banners. Already Anton (no change): OAuth login page (`title`/`h1`), SPA `index.html` `<title>`, `docker-compose.yml` service/image, `deploy/Caddyfile`.
- DB filename intentionally kept (`~/anton-data/shoe_deals.db` — Litestream replica path keys off it). Repo name + folder + DB filename retained pending R2/R3. E6 amended to "partially superseded" (design_decisions.md; tech_debt 2.4, refactor L4b, project_state, domain_model glossary updated).
- Acceptance grep clean: remaining `running-shoe-deals` hits are only the retained repo/folder/path names and historical `docs/archive`/`changelog` mentions. Suite 372; `vite build` clean.

**R2 — GitHub rename (you, ~2 min):**
1. GitHub → repo → Settings → rename to `anton` (or `gh repo rename anton` with gh CLI). GitHub auto-redirects the old name for clones/fetches/issues.
2. Update the local remote anyway (redirects are a crutch): `git remote set-url origin git@github.com:<you>/anton.git`.

**R3 — Local folder rename (you, ~10 min — this is the breaking one):**
1. Quit Claude Desktop and any Claude Code sessions rooted in the repo.
2. `mv ~/Workspace/claude-code/running-shoe-deals ~/Workspace/claude-code/anton`
3. **Recreate the venv** (venvs embed absolute paths): `cd anton && rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt`.
4. Update every absolute path that references the old folder: Claude Desktop MCP config (`claude_desktop_config.json` — the Anton server entry and Filesystem allowed dirs if repo-scoped), any launchd/cron entries, editor workspaces, `frontend` `.env` if it hardcodes paths.
5. Sanity pass: backend boots (`alembic upgrade head` runs), suite green, SPA builds, Claude Desktop lists Anton tools.

**R4 — Docs:** design_decisions E6 → Superseded (record the rename + what deliberately kept the old name: DB filename); changelog entry; project_state repo-name line.

---

## 5. Next steps for the application (resequenced 2026-07-14 — defects lead, RA1.5 parked)

1. ~~**Defect block A (scraper honesty):**~~ ✅ **Done 2026-07-14** — D8 (OOS qualification guard + Shopify pessimistic default, 3 tests) + D2 (confirmed already fixed, comment cleaned up) + D7 (composite kids filter + youth-size exclusion, 26 tests). Suite 323 → 352.
2. ~~**Defect block B (data integrity):**~~ ✅ **Done 2026-07-14** — D1 (FK pragma + `rotation.delete_owned_shoe()` + 10 tests) + D3/D4 batch (verified COROS dedup, fixed 3 code hazards) + D5 (sparkline confirmed not built) + D6 (env-leak fix). Suite 352 → 362. Two `mx:` commits.
3. **I1 New-Retailer Onboarding Agent** — natural follow-on to block A since it reuses the same dry-run/health plumbing just touched.
4. **RA1.5 + §0 queue** — resumes once the hosting decision (Fly.io vs Hetzner CX22, D0) is made. Note D1, D7, D8 all improve what gets deployed, so the deferral has a silver lining.
5. **RA1.6** docs reconciliation (U4) after cutover.
6. **Rename** (§4) around cutover.
7. **RA2 begins to matter:** remote SPA behind real session auth, then the PWA pass — the stepping stones to R5.1 native. Own plan doc when scheduled (roadmap RA2).
8. **R3.5 revisit trigger watch:** now that R4.1 nightly scraping runs unattended, the first "the watchdog fired / a deal alert existed and I never saw it" moment is the designed trigger to build the notification channel — which then unblocks roadmap R4.2 (agent scheduling) and R4.3 (COROS sync nudge).
9. **Debt block:** T1+T2 (the serializer unification — biggest remaining structural item), then T3–T7 as filler tasks.
10. **R5 horizon:** R5.3 purchase-loop closure is the cheapest narrative win (watch → buy → run → retire → replace); R5.4/R5.5 (FIT-file depth, longitudinal analytics) follow felt data needs.

---

*Maintenance note: strike rows here as they land (with dates), mirror into `docs/changelog.md`/`project_state.md`, and delete this file (to `docs/archive/`) when §1–§4 are exhausted.*
