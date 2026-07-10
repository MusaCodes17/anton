# Anton — Technical Debt Report (Prompt 8)

**Companions:** `refactoring/refactor.md` (Prompt 6 — actionable findings with solutions; the detail behind many entries here), `refactoring/dead_code.md` (Prompt 7 — the deletion inventory), `docs/architecture.md` §15/§16, `docs/dependency_graph.md` §§7–11, `docs/design_decisions.md` (verdicts), `docs/domain_model.md` §4 (the invariants everything is ranked against), `CLAUDE.md` (the conventions deviations are judged against), `docs/project_state.md` §6/§7.
**Generated:** 2026-07-06, against the post-Phase-5 tree. **Freshness verified this session:** `models.py` at 18,151 bytes (canonical `Activity`, attribution-only `ShoeRun`); top of `docs/changelog.md` shows nothing newer than the 2026-07-04 Phase-5 entries. **Re-stamped 2026-07-06 evening (docs reconciliation):** tree now at the MSRP-drives-deals state (`models.py` 18,858 bytes · suite 64 · migration `d4e5f6a7b8c9`); the change touched deal qualification/savings paths only — P0/P1 rotation findings stand; **P1-4 narrowed** and **§9.5 struck**, **§9.7 resolved** below.
**Scope:** The **complete ranked catalogue** of technical debt — including debt that is accepted, deferred, or decided. This file is the ledger future sessions consult to understand what they're inheriting and why. It is *not* a review (`refactor.md` has the actionable findings with solutions and effort estimates) and *not* a deletion list (`dead_code.md`). Where an item has a detailed write-up elsewhere, this file ranks and cross-references it rather than restating it. Decided trade-offs (design_decisions ⚠️/🕐 verdicts) are catalogued with their verdict noted — they are ranked by eventual cost, not re-argued.

**How this was produced:** synthesized from the prior audit passes (refactor.md's line-level review, dead_code.md's full-repo inventory, the docs suite's structural audits) plus targeted verification this session — not a fresh line-by-line read. Entries carried from structural-only review are flagged *(verify)* where that matters.

---

## Severity scale and ranking method

Ranked per the program's criteria, in priority order:

1. **P0 — Invariant violations.** Anything that can corrupt the mileage ledger, double-count a run, or bypass a single-write-path (domain_model.md §4). P0 regardless of category.
2. **P1 — Silent failure modes & roadmap blockers.** Traps that produce wrong answers with no error; coupling that gates scheduled R-work (agents, mobile, MCP parity). Security keeps the priority `refactor.md` assigned it.
3. **P2 — Structural debt with a named trigger or scheduled fix.** Wrong-shaped but currently contained; most ⚠️/🕐 decisions live here.
4. **P3 — Hygiene.** Cheap, low-consequence, batched into sweeps.

**State column:** `Active` = live hazard in today's code paths · `Accepted` = decided trade-off (verdict cited) · `Scheduled` = ⚠️ verdict / roadmap item exists · `Dormant` = only bites if a dormant path revives · `Verify` = claim rests on structural review; confirm before acting.

---

## 0. The ranked ledger (cross-category index)

Every P0/P1 item in one place, worst first. P2/P3 items are ranked within their category sections below.

| Rank | Debt item | Category | State | Detail |
|---|---|---|---|---|
| ~~**P0-1**~~ | ~~Writable `current_mileage`/`starting_mileage` via generic `PUT /owned-shoes/{id}`.~~ **Resolved 2026-07-07 (r2:, Phase 2 Session C):** both fields removed from `OwnedShoeUpdate`; manual override moved to sanctioned `rotation.adjust_mileage()` / `POST /owned-shoes/{id}/adjust-mileage` (journals the drift as a note); `starting_mileage` now immutable post-create. Regression in `tests/test_owned_shoes.py`. | Fragile areas (§11.1) | **Resolved** | refactor.md **C1** (struck) |
| ~~**P0-2**~~ | ✅ **RESOLVED (R2.1, 2026-07-07).** Shared bearer token on `/api`+`/mcp` (pure-ASGI middleware), `127.0.0.1` default bind, SPA+Desktop+loopback all send it; 13 HTTP-layer tests. E1 → Superseded by E7. *Still open, separately:* rate limiting on the chat proxy (R2 item) and CORS wildcard tightening (intentionally deferred — see refactor.md C2). | Architectural (§1.1) | **Resolved** (E7) | refactor.md **C2**; arch §11/§15.1 |
| **P1-1** | `ShoeRun` proxy N+1 **live in today's endpoints** (runs list, MCP runs tools, resources — ~81 queries for an 80-run shoe) + proxied attributes silently no-ops in `.filter()`. The double trap: invisible at call sites, and it normalizes the pattern for the next reader. | Fragile areas (§11.2) | **Active** | refactor.md **H4**; dep_graph §8.2; B5 🕐 |
| **P1-2** | Orphan retirement retires live deals on partial detail-fetch failure — `seen_urls` records only *successful* detail fetches, so one 10-s timeout retires that product's deal. B10's "never mass-extinguish" promise is only partially delivered; feed silently under-reports between manual scrapes. | Fragile areas (§11.3) | **Active** | refactor.md **H2** |
| **P1-3** | `DELETE /owned-shoes/{id}` bypasses rotation semantics (orphaned activities linger; `planned_shoe_id`/gear-mapping refs dangle) **and** SQLite FK enforcement is off process-wide (`PRAGMA foreign_keys` never set) — every FK in the schema is advisory. | Fragile areas (§11.4) | **Active** | refactor.md **H3** |
| **P1-4** | Deal domain **nearly untested** *(narrowed 2026-07-06: `test_deals.py` pins MSRP savings/refresh/no-MSRP→no-deal)* — retirement/requalification (4.2), orphan guard (B10), promo manual-beats-scraped (D6) still uncovered: much of the domain constitution enforced by convention plus nothing. Compounding: no HTTP-layer tests anywhere, and `conftest` builds schema via `create_all` so migrations are never exercised. | Missing tests (§8.1) | **Active** | refactor.md **H1** |
| **P1-5** | `shoe_type` free-string vocabulary — the load-bearing cross-domain join key. **`shoe_type` half resolved (R2.4, 2026-07-08):** single backend source (`app/utils/shoe_types.py`), served at `GET /api/shoe-types`, validated on the write schemas (off-vocab → 422); `lib/shoeTypes.js` reduced to presentation-only; MCP/chat-prompt mentions are descriptive text, not a value store. **Still open:** owned-shoe `status` has no boundary validation. | Fragile areas (§11.5) | **Partially resolved** (shoe_type done; `status` open) | refactor.md **M2** (status); B3 🕐; domain_model §4.3 |
| **P1-6** | `mcp_server.py` god object: ~20 tools + 7 resources + 1 prompt + hand-rolled serializers + **embedded business rules** (600/700/800 km threshold messages, review-prompt template) that REST clients can never see. | God objects (§4.1) | **Active** | dep_graph §9.3/§10.4; refactor.md H5 |
| **P1-7** | Two serialization systems for the same aggregates (Pydantic REST + `_*_to_dict` MCP); the owned-shoe shape exists in ≥3 renderings kept in agreement by hand — the standing source of the next numbers-disagree bug in a project whose founding discipline is "correct numbers, once." | Poor abstractions (§5.1) | **Active** | dep_graph §9.4 |
| **P1-8** | ~~Provider agentic-loop triplication in `chat_service` (~100 lines × 3) + model catalogs duplicated router-vs-service.~~ ✅ **Resolved 2026-07-10** — `BaseLLMProvider.run()` owns the shared loop; each provider implements 5 focused abstract methods (`_tool_schema`, `_check_configured`, `_prepare_messages`, `_stream_turn`, `_append_tool_results`). `_ToolCall` dataclass normalises cross-provider tool call representation. Model catalog was already single-sourced (R1.5d). | Poor abstractions (§5.2) | **Resolved** | dep_graph §9.6/§8.5; refactor.md H5; C2 🕐 |
| **P1-9** | Dual schema authority: `create_all` at boot + Alembic; nothing forces a model edit to produce a migration. **Precondition** for any further structural migration (and H3's FK pragma belongs in the same `database.py` session). | Architectural (§1.2) | **Scheduled** (A6 ⚠️) | arch §15.5/§16.2 |
| **P1-10** | Fat legacy routers (`watchlist` ~100-line reduction, `deals`, `dashboard`) with inline ORM — blocks MCP watchlist parity (the app's main page is invisible to the AI surface) and is where H1's missing tests would naturally land. | Tight coupling (§6.1) | **Active** | dep_graph §10.1/§11.5; refactor.md H5 |

Everything below P1 is ranked within its category section.

---

## 1. Architectural debt

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 1.1 | ~~**No auth ×3 surfaces + `0.0.0.0` default bind**~~ ✅ **RESOLVED (R2.1, 2026-07-07)** | ~~P0~~ | Resolved (E7 ← E1) | Ledger rank P0-2. Shared bearer token on `/api`+`/mcp`, `127.0.0.1` default bind. Detail: refactor.md C2, arch §11. Follow-ups: rate limiting (R2), CORS tighten (deferred). |
| 1.2 | ~~**Dual schema authority** (`create_all` + Alembic + retained `legacy_migrations/`)~~ ✅ **RESOLVED (R2.2, 2026-07-07)** | ~~P1~~ | Resolved (A6 → Superseded) | Ledger rank P1-9. Alembic sole authority (startup `alembic upgrade head`, `create_all` test-only, baseline recreates the schema); `legacy_migrations/` deleted (dead_code §2.2); live DB + backups moved to `~/anton-data/` (dead_code §2.1). |
| 1.3 | **In-memory scrape lock + SSE pub/sub = invisible single-process constraint.** Silently invalid under multi-worker uvicorn; nothing enforces or documents "one worker." | P2 | Accepted (D4/D5 🕐) | Hard gate before APScheduler/E5 is ever wired or any multi-process move. Revisit trigger named in D4. arch §15.2. |
| 1.4 | **Whole-table Python reads** — `unified_activities` loads every row (933 and growing) per call, Home included against its own <200 ms budget; watchlist reduces all price records in Python. | P2 | Accepted (labeled, CLAUDE.md §12) | Becomes P1 the day the Home budget is measured slipping — **measure before moving**. The canonical table makes indexed range queries possible now (arch §16.3). |
| 1.5 | **Chat conversation history in localStorage only** (50-cap, quota-trimmed, device-bound). At odds with the multi-client trajectory; invisible to future server-side agents. | P2 | Scheduled (C8 ⚠️) | arch §16.7. Rises to P1 when agent work starts — agents need shared context. |
| 1.6 | **`MCP_SERVER_URL` loopback self-dependency** — the app cannot answer a chat message unless it can reach *itself* over TCP; change bind/port and chat silently degrades to "No tools available." Nothing marks it self-referential. | P2 | Active | dep_graph §7.3/§8.1/§11.7. Cheapest fix (derive from own host/port + log at startup) is one session. |
| 1.7 | ~~**APScheduler declared, unused** — a dependency without an architecture, inviting drive-by wiring that collides with 1.3's lock assumptions.~~ | ~~P2~~ | ✅ **Resolved 2026-07-07 (R1.6)** | Dropped from `requirements.txt`; scheduling note added to `scrapers/lock.py`. E5 → Superseded; reinstate with an R4.1 design. See changelog 2026-07-07. |
| 1.8 | **Live DB + dated `.bak*` restore points in the working tree** — "which state is canonical" ambiguity; large binaries near git. | P2 | Accepted-practice / Scheduled relocation (E2 🕐) | Keep the *practices* (pre-migration backups, seed export); relocate files per arch §16.2. `.bak-pre-activities` (10.5 MB) stays until the migration ages (dead_code §2.1). |
| 1.9 | **No scrape observability** — no persisted scrape-run/attempt history; "is Altitude quietly broken?" is log archaeology + `last_scraped_at`. | P2 | Active (roadmap: arch §16.6) | The natural substrate for scheduled scraping; forces the 1.3 decision. |
| 1.10 | **Mixed transaction-ownership conventions** — per-method commits (DealStore), self-committing with opt-out (rotation), caller-owned (settings/import). Each locally reasoned; collectively head-held knowledge. Scrape non-atomicity is arguably *desired* — the debt is that the intent is implicit. | P3 | Accepted | Document, don't change (refactor.md H5 last rows; arch §15.10). |

## 2. Naming inconsistencies

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 2.1 | **Mixed `app.models` façade vs `app.models.models` direct imports in the same files** (`shoes.py`, `owned_shoes.py`, others) — and the façade is incomplete (see §9.1), which is how stale exports hide. | P2 | Active | dep_graph §11.4: complete the façade or drop it; one convention. |
| 2.2 | **`shoe_runs` table name now misleading post-Phase-5** — it's an attribution row, not a run record. Continuity-of-meaning-over-naming-purity was an explicit decision; the glossary (domain_model §7.1) carries the disambiguation. | P3 | Accepted (B5 🕐) | Cost is per-new-reader confusion; the glossary mitigates. Rises only if the proxy-shrink (§5.4) renames anyway. |
| 2.3 | **Two pace representations reachable in storage** — canonical int s/km on `activities` vs legacy `"M:SS/km"` strings in old `shoe_runs`-era comments/fields. Convention says any string pace in storage is legacy (domain_model §7.2). | P3 | Active, shrinking | Resolves with the proxy-surface shrink; the pure `pace` module (§5.5) is the enabler. |
| 2.4 | **Pre-rebrand names**: repo `running-shoe-deals`, API title "Running Shoe Deal Finder", DB filename; also the chat `SYSTEM_PROMPT` still introduces the assistant by the old product name (the one *user-visible* instance — refactor.md L4b). | P3 | Accepted (E6 ✅) | Decided; note the SYSTEM_PROMPT line is the cheap exception worth fixing since the assistant is a user surface. |
| 2.5 | **Small conformance strays**: `conftest.py` docstring still says "Strava-import test suite"; `datetime.utcnow()` (naive, deprecated) in `scraping.py`/`base_scraper` vs `datetime.now(timezone.utc)` everywhere else; `ScrapeRequest`/`ScrapeResult` imported-never-used in `scraping.py`. | P3 | Active | refactor.md H1/L4c; dead_code §6.2. Batch into any passing sweep. |

## 3. Large files

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 3.1 | **`mcp_server.py`** — the whole MCP surface in one module (tools + resources + prompt + serializers + business rules). Also a god object; ranked there (§4.1, ledger P1-6). | **P1** | Active | dep_graph §9.3. |
| 3.2 | **`models/schemas.py`** — every Pydantic schema for every domain in one file; `ShoeNote` schemas stranded in the COROS section under an empty header; duplicate-era fields (`size_available` + `sizes_available`); dead schemas inventoried in dead_code §6.2. Also carries the heavyweight `DealResponse` (see §11.8). | P2 | Active | refactor.md M1. Split-by-domain is natural when the fat-router extractions (§6.1) create per-domain services. |
| 3.3 | **`services/rotation.py`** — the rotation hub that also imports `Deal`/`PriceRecord`/`Shoe`. Size is a symptom of the cross-domain concentration; ranked as coupling (§6.2). | P2 | Accepted-by-design concentration | dep_graph §9.1. |
| 3.4 | **`routers/owned_shoes.py`** — hosts `_attach_computed_fields` + the checkpoint-constant re-export that `coros_sync` imports (Task D). A router doing shared-library duty. | P2 | Active | dep_graph §10.2/§11.1; resolves with Task D (§6.3). |
| 3.5 | **`services/chat_service.py`** — large because the loop is written three times; ranked as the triplication (§5.2, ledger P1-8). | — | — | Cross-ref only. |

## 4. God objects

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 4.1 | **`mcp_server.py` monolith adapter** — imports models + scrapers + five services; owns a second serialization system; embeds business rules (mileage-threshold messaging, review-prompt template) invisible to the REST surface, violating the module's own thin-adapter docstring and CLAUDE.md §4.1. | **P1** | Active (ledger P1-6) | Fix direction: thresholds move beside `RETIREMENT_THRESHOLD` in `rotation`; serializers unify with §5.1. dep_graph §11.6. |
| 4.2 | **`rotation.py` as the everything-hub** — correct as the run-domain write-path owner; the god-object aspect is that it *also* owns the deals-domain bridge (`active_deal_counts_by_type`, `find_matched_image`), so the two domains can never be separated without dragging it along. | P2 | Accepted-by-design ("the heuristic bridge") | dep_graph §9.1. The debt is concentration, not incorrectness; extract the bridge functions if domain separation is ever wanted. |
| 4.3 | **`BaseScraper` as a kitchen-sink base** — fetching (requests + Playwright), price/size parsing, stock heuristics, kids filtering, promo regex, Algolia credential rediscovery in one class. Deliberate (D6 centralizes hygiene) and it works; listed because `admin.py` reaching in for `is_kids_shoe` as a *data-cleanup rule* (§6.4) shows the class already leaks responsibilities beyond scraping. | P3 | Accepted (D1/D6 ✅) | Only act if a second non-scrape consumer appears. |

## 5. Poor abstractions

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 5.1 | **Two serialization systems for the same aggregates** (Pydantic + `_*_to_dict`), ≥3 renderings of the owned-shoe shape. | **P1** | Active (ledger P1-7) | Landing spot: the shared shaping function Task D creates (§6.3). |
| 5.2 | **Provider loop triplication + duplicated model catalogs.** | **P1** | Active (ledger P1-8) | C2 🕐's own verdict: "consider whether three loops still pay rent at next protocol change" — the agents *are* that change. |
| 5.3 | **`ShoeRun` property proxies** — a compatibility bridge presenting as real columns. As an abstraction: presentation logic (`avg_pace` formatting) now lives in the ORM class (layer violation, dep_graph §10.5), and the bridge's costs are the §11.2 traps. | **P1** (via its hazards) | Accepted **as a bridge, not a permanent API** (B5 🕐) | arch §16.4 is the shrink plan; eager-loading at seams (refactor.md H4) is step one. |
| 5.4 | ~~**`scraper_manager.py` compat shim** — pure re-exports; real orchestrator/lock/registry boundaries invisible at all four call sites.~~ | ~~P2~~ | ✅ **Resolved 2026-07-07 (R1.5b)** | Shim deleted; all five consumers import `ScrapeOrchestrator`/`lock`/`registry` directly. D7 → Superseded. See changelog 2026-07-07. |
| 5.5 | ~~**Pace formatting ×3** (`rotation`, `coros_client`, the `ShoeRun.avg_pace` proxy) — one formatting rule, three copies that can drift.~~ | ~~P2~~ | ✅ **Resolved 2026-07-07 (R1.5c)** | Extracted pure `app.utils.pace`; the three sites re-import it. `rotation.*` kept as thin re-exports. See changelog 2026-07-07. |
| 5.6 | **COROS shoe-suggestion heuristic implemented twice with different rules** — the canonical pace-primary tables in the `sync_coros_runs` prompt vs `CorosSyncModal.jsx`'s simpler threshold heuristic. Two engines, different answers for the same run. | P2→Dormant | Dormant (modal fronts the C6-dormant server path) | dead_code §4.1. Reconcile (serve suggestions from the backend) **before** any revival of the server path. |
| 5.7 | ~~**Hard-coded model catalog in `routers/chat.py` vs prefix routing in `chat_service`** — two files encode one fact.~~ | ~~P2~~ | ✅ **Resolved 2026-07-07 (R1.5d)** | Single-sourced as `chat_service.MODELS`; `/providers` groups it and `_get_provider` looks up provider by id (no prefix matching). Provider-loop triplication (§5.2) is separate and still open. See changelog 2026-07-07. |
| 5.8 | **Frontend micro-duplication**: relative-time formatter ×2; four page-local stat-tile components (the latter is stated convention, only act when one next changes). | P3 | Active / Accepted | dead_code §4.2/§4.3. |

## 6. Tight coupling

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 6.1 | **Fat routers with inline ORM** (`watchlist`, `deals`, `dashboard`) — API layer coupled directly to the schema, and the coupling *blocks roadmap work*: MCP cannot expose the watchlist because its logic lives in a router. | **P1** | Active (ledger P1-10) | dep_graph §10.1/§11.5. Extraction also unlocks §8.1's tests naturally. |
| 6.2 | **`rotation` imports `Deal`/`PriceRecord`/`Shoe`** — the single point where the two deliberately-independent domains meet in code. | P2 | Accepted-by-design | See §4.2. The B1 no-FK principle stands; the code concentration is the (tolerable) price. |
| 6.3 | ~~**Task D leftover: `coros_sync → owned_shoes._attach_computed_fields`** — private-helper import between sibling routers; response-shaping logic trapped in a router another router needs.~~ | ~~P2~~ | ✅ **Resolved 2026-07-07 (R1.5a)** | Promoted to `rotation.attach_computed_fields`; the router→router import is gone. See changelog 2026-07-07. |
| 6.4 | **`routers/admin` → `BaseScraper.is_kids_shoe`** — data hygiene coupled to scraper internals. | P3 | Active, self-resolving | The whole `admin.py` router is slated for deletion after one final no-op run (dead_code §5.2), which removes this edge. |
| 6.5 | ~~**All four scraper consumers coupled to the `scraper_manager` shim.**~~ | ~~P2~~ | ✅ **Resolved 2026-07-07 (R1.5b)** | Same item as §5.4, from the consumer side. See changelog 2026-07-07. |
| 6.6 | **Frontend↔backend contract as matching string literals** — no generated client, no shared types; SSE event schemas duplicated as literals on both sides; `lib/shoeTypes.js` a by-value copy of the join-key vocabulary. | P2 | Accepted (A5 🕐) | Revisit trigger is the mobile client (a second consumer). The `shoeTypes.js` copy specifically is part of P1-5's fix. dep_graph §6/§8.4. |

## 7. Circular dependencies

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 7.1 | **Hard Python import cycles: none.** The import graph is a verified DAG (dep_graph §7). Recorded so future sessions know the baseline to preserve. | — | Healthy | — |
| 7.2 | **Near-cycle: `coros_sync → owned_shoes`** — one refactor away (if `owned_shoes` ever needs sync status, the cycle appears). | P2 | Active | Same fix as §6.3 (Task D). dep_graph §7.1. |
| 7.3 | **Runtime cycle: `chat_service → HTTP → /mcp → this same process`** — acyclic imports *because the cycle was pushed onto the network*. Works; genuinely self-dependent. | P2 | Active | Same item as §1.6; C1's verdict keeps the architecture, makes the loop explicit or in-process. dep_graph §7.3. |
| 7.4 | **Future-cycle point: `app.models/__init__` aggregating models + schemas** — safe today; a "schema needs an ORM enum" import would create circularity through the package. | P3 | Latent | dep_graph §7.2. Resolving §2.1 (one import convention) removes the pressure. |
| 7.5 | **Protocol-level sampling loop** (`draft_shoe_review` → client LLM → possible tool calls back) — bounded by the client, not Anton. | P3 | Accepted (C7 ✅) | Informational. |

## 8. Missing tests

The suite (64 passing as of 2026-07-06 — live count in the changelog/project_state) covers the rotation/training domain well — including, verified this session, the **retirement pipeline and replacement-deal heuristic at service level** (`test_rotation_overview.py` locks in the 75% threshold, worst-first ordering, and type-match heuristic). The gaps are concentrated and asymmetric:

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 8.1 | **Deal domain: nearly untested** *(narrowed 2026-07-06 — `test_deals.py` pins the MSRP rules)* — retirement/requalification, orphan guard, promo protection remain uncovered. The most complex write path in the system, the code most likely to be touched under pressure (retailer breaks at 11 pm), thin net. | **P1** | Active (ledger P1-4) | refactor.md H1 has the one-session test plan (stub-scraper truth table, MSRP-based). |
| 8.2 | **No HTTP-layer tests at all** — every test calls services/handlers directly; routing, DI, and Pydantic serialization are unexercised. The one recorded production 500 lived exactly in that layer. | P2 | Active | refactor.md H1's second slice: a `TestClient` smoke module. |
| 8.3 | **Migrations never exercised** — `conftest` builds schema via `create_all`, so the Alembic path the live DB depends on has no automated check. Compounds §1.2. | P2 | Active | Resolve alongside A6 (create_all demoted to fixtures makes this explicit rather than accidental). |
| 8.4 | **No scraper unit tests — by deliberate decision** (CLAUDE.md §10: no brittle HTML-fixture tests; live verification via dry-run endpoints). The risk accepted: regressions in shared parsing/qualification logic surface only in live scrapes. §8.1's orchestrator tests (stub scraper, no DOM fixtures) cover the highest-value slice *within* the decision. | P3 | Accepted | Documented risk, ranked low because the dry-run tooling is real mitigation. |
| 8.5 | **Frontend: no test harness** — the bar is `vite build` clean + 0 console errors + visual pass. Fine solo; the L3 invalidation nits (refactor.md) are the kind of thing a harness would catch. | P3 | Accepted (CLAUDE.md §10) | Revisit alongside A5's TypeScript trigger (mobile client). |

## 9. Missing documentation

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 9.1 | **`models/__init__.py` façade missing the entire Phase-5 era** (`Activity`, `PlannedRace`, `StravaGearMapping`, race/strava schemas…) while exporting schemas nothing uses. Stale façades are how dead exports hide. | P2 | Active | dep_graph §11.4; dead_code §4.5. Same fix as §2.1. |
| 9.2 | **No INVARIANTS section anywhere** codifying domain_model §4 as checkable statements future work must verify against. The strongest properties in the system are enforced by convention + scattered tests; P0-1 is what that looks like when it fails. | P2 | Active (arch §16.9) | Cheap insurance; natural home is CLAUDE.md or architecture.md. |
| 9.3 | **MCP `_*_to_dict` serializers have no docstrings** — in the one module where docstrings are the LLM-facing contract (CLAUDE.md §13). | P3 | Active | Moot if §5.1's unification lands first. |
| 9.4 | **`strava_stats → activities._effective_moving_s`** — private-by-convention function imported cross-module, undocumented; a "safe" rename inside `activities.py` breaks stats. | P3 | Active | dep_graph §8.9. One comment, or promote the function. |
| 9.5 | ~~**Deal "savings" semantics undocumented**~~ **Struck 2026-07-06** — resolved differently: savings are now measured against MSRP (B9-v2, changelog 2026-07-06), making the semantics self-describing; refactor.md L2 struck with the same pointer. | P3 | Resolved | — |
| 9.6 | **`_fetch_with_browser` config-dormant, unmarked** — every constructor hard-codes `use_browser: False`; the path looks live and is actually config-reachable-only. | P3 | Dormant | dead_code §10.1: one comment. |
| 9.7 | ~~**`docs/changelog.md` bottom reference sections likely stale** *(verify)*~~ **Confirmed and fixed 2026-07-06** — the stale tail (old schema/API overviews, target_price deal semantics, retired `/scrape/test/*` endpoints) was amputated and replaced with a pointer into `docs/`; the Retailer Status table was relocated to `architecture.md` §10 first; the header was retitled to "Anton — Session Changelog." | P2 | Resolved | R1.2 executed in the docs-reconciliation session. |

## 10. Missing typing

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 10.1 | **No TypeScript on the frontend** — the API contract is grep-verified, not compiler-verified. | P2 | Accepted (A5 🕐) | **Named revisit trigger: the mobile client** — a second consumer is when a generated/typed contract starts paying for itself. Don't introduce piecemeal (CLAUDE.md §5). |
| 10.2 | **`Retailer.scraper_config: Optional[dict]`** — untyped blob; no schema validation for the Algolia credential shape it carries; the model comment still describes the retired CSS-selector era (dead_code §3.1). Fragile-adjacent: a malformed config surfaces as a scrape-time failure, not a write-time 422. | P2 | Active | A small TypedDict/Pydantic shape + comment fix. |
| 10.3 | **Older service modules may lack return-type annotations** (`rotation.py`, `home.py` named as candidates) *(verify)* — CLAUDE.md §5 requires hints on all service signatures; these predate it. Not re-verified line-by-line this pass. | P3 | Verify | Check before batching into a sweep; may already be clean. |

## 11. Fragile areas

Anything that could silently violate a §4 invariant lives here regardless of other classification.

| # | Item | Sev | State | Notes |
|---|---|---|---|---|
| 11.1 | **The writable mileage ledger** (`OwnedShoeUpdate.current_mileage` + blind setattr; `starting_mileage` edits don't delta the counter; two-step confirm exists only in the browser, not the API; `status` also pattern-unvalidated). The single most dangerous schema exposure — and an *undocumented invariant exception*, since the UI uses it deliberately. | **P0** | **Resolved 2026-07-07** (ledger P0-1) — `rotation.adjust_mileage()` sanctioned path shipped; ledger no longer writable via PUT. `status` pattern-validation deferred to M2 (vocabulary). | Full analysis + revised fix: refactor.md **C1** (struck). |
| 11.2 | **ShoeRun proxy traps** — live N+1 on today's run-list endpoints; silent no-op in `.filter()`; code that works and code that breaks look identical in grep. An *active trap for new code*, flagged as such in project_state §6.2 and CLAUDE.md §6. | **P1** | Active (ledger P1-1) | refactor.md **H4** (the `contains_eager` helper); arch §16.4. |
| 11.3 | **Orphan-retirement partial-failure gap** — routine detail-fetch timeouts retire live deals; self-healing on next scrape, but "next scrape" is manual and can be days; also erodes `detected_at` honesty. | **P1** | Active (ledger P1-2) | refactor.md **H2** (track search-returned URLs; tests first). |
| 11.4 | **Shoe deletion + advisory FKs** — cascade bypasses delete-run semantics; orphaned activities pollute the training feed; dangling `planned_shoe_id`/gear refs resolve silently to `None` because `PRAGMA foreign_keys` is never enabled. | **P1** | Active (ledger P1-3) | refactor.md **H3** (pragma hook + `rotation.delete_owned_shoe`; run `foreign_key_check` first). |
| 11.5 | **`shoe_type`/`status` vocabulary: 4 copies, zero validation** — typos degrade the replacement-deal bridge and the rotation feeds invisibly. | **P1** | Active (ledger P1-5) | refactor.md **M2** (interim `SHOE_TYPES` constant + `Literal`); full fix arch §16.5. |
| 11.6 | **Prompt-vs-practice drift in `sync_coros_runs` + dedup asymmetry** — the shipped prompt's Step 6 says `confirm_coros_run`; practiced protocol logs via `log_run_to_shoe`, which doesn't expose `coros_activity_id` — so practiced syncs are protected only by the date/±0.1 km fallback tier. Invariant-adjacent (§4.7 never-double-count) but fallback-guarded; ranked with refactor.md's judgment. | P2 | Active (verify live tool behavior) | refactor.md **M5**: one verification session; two-line MCP-tool fix makes either path dedup-safe. |
| 11.7 | ~~**Scrape-lock wedge**~~ **Resolved 2026-07-07 (r2:, Phase 2 Session C):** whole `run_scrape_job` body moved under the lock-releasing `finally`; tolerant `release_scrape_lock`; added `POST /api/admin/scrape-lock/release` escape hatch + `GET /api/scrape/status`. Regression in `tests/test_scrape_lock.py`. | P2 | **Resolved** | refactor.md **M3** (struck). |
| 11.8 | **Per-row query fan-out on the most-read aggregates** — `_attach_computed_fields` fires 2–3 queries per shoe per list; `DealResponse` embeds full `RetailerResponse` whose `active_promo_codes` property lazy-loads per deal row; the rotation resource (with its fan-out) is pre-loaded into **every** chat conversation start. | P2 | Active | refactor.md **M4** + **M1(b)**; fix inside Task D's shared shaping function. |
| 11.9 | **Sync scrape endpoints hold an HTTP request + DB session open 20–30 min** — the 35-minute axios timeout is the only safety valve; MCP full-catalog `trigger_scrape` reliably times out client-side (known quirk, worked around). | P2 | Accepted at current posture | arch §10; project_state §6.1. Resolves properly only with the observable-job-system direction (§1.9). |
| 11.10 | **Algolia credential rediscovery depends on the retailer's search UI not changing** — the self-healing mechanism has its own single point of failure; Playwright is a hard operational dependency of recovery. | P2 | Accepted (D2 ✅ — structural) | No action; recorded so a rediscovery failure isn't treated as novel. |
| 11.11 | **External COROS MCP tool-schema dependency** — the `sync_coros_runs` prompt names a third party's tool names/parameters; a rename on COROS's side breaks the sync workflow with zero signal in this repo. | P2 | Accepted (C6 🕐 — the pragmatic optimum) | dep_graph §8.6. Mitigation is procedural: the sync protocol's step 1 fails loudly in practice. |
| 11.12 | **Dormant-path landmines for C6 revival** — `coros_client.activity_to_run_dict` derives a **UTC date** (violates B14; shifts evening runs a day) and the CorosSyncModal heuristic disagrees with the canonical one (§5.6). Zero live risk today; guaranteed bugs on revival. | P3 | Dormant (recorded in dead_code §9.1) | Both must be fixed before the server path ever goes live. |
| 11.13 | **Function-level imports in `routers/scraping.py`** — real dependencies invisible to top-of-file audit; three of them vanish with the `/scrape/test/*` deletions (dead_code §5.1). | P3 | Active, mostly self-resolving | dep_graph §8.7/§11.11. |
| 11.14 | **Miscellaneous verified small hazards**: `trigger_scrape`'s advisory notification always reports 0 deals (dict iterated as list — an AI-facing wrong signal); `is_already_logged` compares ISO string to a `Date` column (SQLite-only correctness); `active_promo_codes` sort would `TypeError` on an uncommitted row; brand matching case-sensitive in REST vs `ilike` in MCP. | P3 | Active | refactor.md **L1/L5/L4e**. Batch into the fat-router extraction. |

---

## Reading this ledger: what's decided vs. what's open

- **The standing to-do list of decided change** is design_decisions' ⚠️ set — **E1 (auth), A6 (schema authority), C8 (chat memory)** — all catalogued above with their ranks. (D7 shim and E5 APScheduler were executed 2026-07-07, R1.5b/R1.6.) These flip to Superseded entries as they're executed; strike the entries here in the same session.
- **The 🕐 set** (A2 SQLite posture, A5 no-TS, B3 free-string bridge, B5 proxies, C2 provider strategy, C6 COROS path, D4 lock, E2 backups) are *conditional* debt: each carries a named revisit trigger in design_decisions.md. Nothing in this catalogue re-argues them — it ranks their eventual cost and records what tightens the trigger (agents → C2/C8; mobile → A5/E1; scheduling → A2/D4/E5).
- **The open, undecided items** — everything marked Active without a verdict — are concentrated where the docs predicted: the deal-domain edges (11.3, 8.1), the Phase-5 proxy seams (11.2, 5.3), and the adapters (4.1, 5.1). refactor.md's sequencing note is the starting order: C1 + M3 same-day; H2+H1 one session; H3 one session; H4+M4 as the proxy-seams session.

**Honest-uncertainty register (verify before acting):** §10.3 (older service annotations), §11.6 (live `confirm_coros_run` behavior), and everything refactor.md's own header lists as structurally-reviewed-only (`algolia_scraper.py`, `home.py`/`strava_stats.py`/`strava_import.py` internals, remaining page components). Nothing in this catalogue rests *solely* on unverified ground except where flagged. (§9.7 was on this register; verified and resolved 2026-07-06.)

---

*Maintenance note: this file is the index; `refactor.md` and `dead_code.md` are the detail. When debt is paid, strike the entry with a changelog pointer (don't delete) so the final documentation review can see found-vs-remaining; when a ⚠️ decision executes, flip it here and in design_decisions.md in the same session. New debt gets an entry with a severity and a state, even (especially) when it's accepted — the ledger's value is completeness, not urgency. Re-verify P0/P1 ranks if `models.py` changes size (18,858 bytes as of the 2026-07-06 re-stamp) or a changelog entry newer than 2026-07-06 MSRP-drives-deals appears.*
