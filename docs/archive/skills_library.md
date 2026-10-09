# Anton — Skills Library Design

**Deliverable of documentation prompt 5.** This is a **design, not an implementation**: it specifies the skill files to create under `.claude/skills/`, and for each one its purpose, trigger, required context, workflow outline, common mistakes, and checklist — in enough detail that a later session (or a cheaper coding agent, per roadmap R5.6) can write each file without re-deriving the project's conventions.

**Relationship to existing `.claude/commands/`:** commands are *imperative shortcuts* ("run the thing"); skills are *workflow knowledge* ("how we do this kind of change here"). The one existing command, `/project:migrate`, stays — skill `S03` references it rather than duplicating it. Note: only `migrate.md` exists on disk today (the changelog's former Project Commands table, which listed five, was corrected in the 2026-07-06 tail prune); the skills below absorb the intent of the missing ones (`add-retailer` → S05) rather than resurrecting them separately.

**Authoring conventions for the skill files (when implemented):**
- Location: `.claude/skills/<name>.md`, kebab-case names matching this design.
- Each file follows the same six sections used below, in order.
- Skills cite the canonical docs (`CLAUDE.md` §s, `docs/*.md`) instead of restating them — a skill is a *path through* the conventions, not a second copy of them. Restated rules drift; citations don't.
- Every skill ends with the shared session checklist reference (CLAUDE.md, "Session Checklist") plus its own specific items.

---

## Proposed structure

```
.claude/skills/
    add-service-capability.md      S01 — the master workflow (service → REST → MCP)
    add-api-endpoint.md            S02 — thin-router endpoint over an existing service
    add-database-model.md          S03 — schema change with migration discipline
    data-migration.md              S04 — structural/data-moving migrations (the E4 bar)
    add-retailer.md                S05 — new scraper, platform detection → verification
    add-mcp-tool.md                S06 — tools/resources/prompts + parity rules
    ai-agent.md                    S07 — agent prompts & the confirmation protocol
    add-frontend-page.md           S08 — page/hook/api-client pattern + mobile pass
    write-tests.md                 S09 — what to test and how, per feature type
    refactor-service.md            S10 — seams, shims-with-expiry, behavior contracts
    background-job.md              S11 — long-running work, locks, SSE progress
    debugging.md                   S12 — where truth lives when something's wrong
    session-wrapup.md              S13 — changelog + docs-suite maintenance ritual
```

Deliberately **not** included: `deployment.md` (there is no deployment — Anton is local-first by design decision A1; a deployment skill would document a fiction. R5.2 creates the need; write the skill then).

---

## S01 — `add-service-capability.md` *(the master skill)*

**Purpose:** The end-to-end workflow for adding a new capability: service function → tests → REST endpoint → MCP tool → (optional) UI. Most other skills are steps of this one.
**When to use:** Any feature that adds behavior, not just presentation. If the request is "Anton should be able to X," start here.
**Required context:** `CLAUDE.md` §§2–4, 6; `docs/architecture.md` §7–§9; `docs/domain_model.md` §4–§5 (does an invariant or write-path already own this?).
**Workflow outline:**
1. Locate the owning domain and check `domain_model.md` §5 — does a sanctioned write path already cover this? Extend it (escape-hatch pattern) rather than adding a parallel one.
2. Write the service function (session-first signature, keyword-only options, dataclass result, docstring with commit ownership).
3. Tests for the rule and its boundaries (S09) — *before* any adapter.
4. Thin REST endpoint (S02). 5. Matching MCP tool (S06) — parity is mandatory, not optional. 6. UI if applicable (S08). 7. Wrap up (S13).
**Common mistakes:** logic in the router "just for now"; skipping the MCP twin; recomputing a derived value client-side; new write path instead of a parameter on the existing one; forgetting both surfaces must show identical numbers.
**Checklist:** service has sole ownership of the rule · tests green before adapters · REST + MCP return the same shapes/numbers · docstrings state commit ownership · changelog entry.

## S02 — `add-api-endpoint.md`

**Purpose:** Add a REST endpoint the project way — thin, typed, boundary-attached derivations.
**When to use:** New route over existing/new service logic; also when converting a fat-router pattern.
**Required context:** `CLAUDE.md` §4.1, §7; an exemplar file: `routers/races.py` (thin CRUD) or `routers/home.py` (aggregate); `models/schemas.py` conventions.
**Workflow outline:** pick router file by resource → handler with `Depends(get_db)` → delegate to service → Pydantic response model (`from_attributes` if reading attached fields) → error translation (`LookupError→404`, `ValueError→400/502`) → register in `main.py` if a new router → tests (endpoint-level, per S09) → frontend client function in `api.js` if it will be consumed.
**Common mistakes:** aggregation loops in the handler (the `watchlist` anti-pattern — flagged debt, don't copy); returning bare ORM objects where a schema exists; inventing a second error-shape; forgetting the `/` vs no-slash double-decorator convention where used (`races.py`); adding an endpoint the MCP surface can't mirror (means logic is in the wrong layer).
**Checklist:** handler ≤ ~15 lines · response model or documented shaped-dict · errors translated not leaked · appears in OpenAPI docs · test hits it.

## S03 — `add-database-model.md`

**Purpose:** Add/alter a table or column with the schema disciplines intact.
**When to use:** Any change to `models/models.py`.
**Required context:** `CLAUDE.md` §9; `/project:migrate` command (mechanics); `docs/design_decisions.md` A6 (dual-track caveat), B13 (derived-never-stored); `domain_model.md` §7.2 (naming).
**Workflow outline:** model change (docstring = domain meaning; units in names; server-side stamps) → schema change in `schemas.py` → `alembic revision --autogenerate` → **prune autogenerate noise** (SQLite type-mapping artifacts) → review batch-mode output → apply → update `models/__init__.py` exports if using the façade → tests touching the new shape → note in `docs/architecture.md` §5 table if a new entity.
**Common mistakes:** relying on `create_all` to apply the change to the live DB (it won't — it only creates missing tables); storing a derived value; client-suppliable audit fields; missing the second side of a relationship (`back_populates`); forgetting the `models/__init__` façade export (or mixing import styles — pick per CLAUDE.md §6).
**Checklist:** migration exists and applies cleanly · autogenerate noise pruned · naming conventions held · `alembic downgrade -1` at least drops cleanly for additive changes · docs updated if a new entity.

## S04 — `data-migration.md`

**Purpose:** The heavyweight discipline for migrations that *move or restructure data* — the `canonical_activities` bar (E4).
**When to use:** Any migration beyond additive columns: table merges/splits, backfills, data rewrites.
**Required context:** `docs/design_decisions.md` E4 + B4/B5 (the worked example); `alembic/versions/c3d4e5f6a7b8_canonical_activities.py` as the reference implementation; `CLAUDE.md` §9, §11.
**Workflow outline:** write a §-plan first (what moves, what's invariant, what's the contract — e.g. "counters untouched, response shapes identical") → pre-migration backup `shoe_deals.db.bak-pre-<name>` → reversible `upgrade`/`downgrade` → **reconciliation queries** defined *before* running (counts, sums, per-entity drift) → run on live DB → reconcile pre/post exactly → `downgrade -1` round-trip test → suite green → UI spot-check the affected pages → changelog entry records all numbers.
**Common mistakes:** irreversible downgrade ("we'll never roll back" — the reference migration proved you test it anyway); reconciling after instead of defining checks before; changing behavior in the same change as storage (§11 rule); skipping the backup because "it's quick"; not stating the invariant contract, so nobody can verify it held.
**Checklist:** plan doc/§ entry · named backup exists · downgrade round-trips · reconciliation numbers recorded · behavior-preservation contract stated and verified.

## S05 — `add-retailer.md`

**Purpose:** Bring a new retailer into the scrape pipeline, from platform identification to verified deals.
**When to use:** Adding a store; also when an existing scraper breaks structurally (re-run the identification steps).
**Required context:** `docs/architecture.md` §10; `scrapers/` exemplars by platform (`forerunners.py` Shopify · `altitude_sports.py` Algolia · `enroute_run.py` bespoke); the Retailer Status table in `docs/architecture.md` §10 (relocated from the changelog 2026-07-06); design decisions D1–D3 (especially: **no paid bot-bypass, ever**).
**Workflow outline:** probe platform (`/products.json` → Shopify; search-XHR interception → Algolia; neither → bespoke or walk away) → create via API/UI so `platform_detection` runs → if quirks: subclass in its own file + register in `registry.py` (bespoke-by-name beats dynamic) → respect base-class inheritance (kids filter, politeness sleeps come free — don't reimplement) → verify with `POST /shoes/test` dry-run on a known-on-sale model → full single-retailer scrape → confirm price records + at least one qualified deal end-to-end → update retailer-status table.
**Common mistakes:** overriding `search_products` instead of using `search_products_filtered` (loses the kids filter); hardcoding Algolia credentials (rediscovery exists — wire it, don't pin it); scraping politeness removed "to test faster"; French-locale sites needing `/en` (Boutique Endurance/Le Coureur precedent); fighting Cloudflare (the answer is documented: don't — mark blocked like Sporting Life).
**Checklist:** platform recorded on the Retailer row · dry-run finds the test shoe · one real deal qualified end-to-end · status table updated · no new dependency, no bypass service.

## S06 — `add-mcp-tool.md`

**Purpose:** Extend the MCP surface (tool, resource, or prompt) keeping parity and LLM-facing contracts right.
**When to use:** Alongside every S01 capability; or when the assistant "can't see/do" something REST can.
**Required context:** `docs/architecture.md` §9; `mcp_server.py` exemplars (a read tool, a `{"success":...}` write tool, a templated resource); `CLAUDE.md` §13 (docstring-as-contract); dependency_graph §3 (what the module already imports).
**Workflow outline:** confirm the service function exists (never put logic in the tool) → tool with `get_session()` context manager → docstring written *for the model*: args, semantics, side effects, whether confirmation is required → write tools return `{"success": bool, ...}`; read tools plain data; resources markdown + embedded JSON → `ctx.log` for advisory notifications → verify via Son of Anton (tool auto-discovers — if chat can't see it, the server didn't register it) and via Claude Desktop if templated URIs are involved.
**Common mistakes:** business logic in the tool body (thresholds/messages — flagged debt, don't add more); raising instead of returning `success: False`; a docstring written for humans that leaves the model guessing parameter semantics; forgetting resources are pre-primed into chat context (shape changes ripple into the system prompt's trust rules); assuming FastAPI DI works (it doesn't here — `get_session()`).
**Checklist:** logic lives in a service · envelope convention held · docstring answers "should the model call this and how" · discovered automatically in chat · parity noted in changelog.

## S07 — `ai-agent.md`

**Purpose:** Design agent workflows (MCP prompts / proactive digests) under Anton's automation posture.
**When to use:** Roadmap R3/R4 items (weekly summary, deal alerts, coupon hunting) and any new "Anton does X for you."
**Required context:** `docs/design_decisions.md` C6, C9 (non-negotiable); the `sync_coros_runs` prompt as the reference protocol; `docs/domain_model.md` §5.3, §5.5; roadmap R3 for sequencing.
**Workflow outline:** state what the agent *reads* (existing tools/resources only — if a read is missing, that's an S01/S06 prerequisite) → state what it may *write* (must be an existing gated path) → encode the protocol as numbered steps: fetch → dedup → suggest **with the heuristic stated** → present → **WAIT for confirmation** → write via sanctioned tool → summarize → threshold/advisory check → decide the surface (prompt in the + menu, Home module, R3.5 channel) → dry-run the full protocol conversationally before calling it done.
**Common mistakes:** auto-writing "because the confidence is high" (C9 has no confidence exception); inventing data when a tool returns empty (the prompt must say "never invent"); burying the suggestion heuristic so the runner can't audit it; building delivery infrastructure before the on-demand version proves value (roadmap ordering); giving the agent a personality at the expense of the protocol.
**Checklist:** reads = existing tools · writes = existing gated paths · explicit WAIT step · heuristics stated in the prompt text · dry-run transcript sane · C9 compliance re-read.

## S08 — `add-frontend-page.md`

**Purpose:** Add or rework a page/feature in the SPA the project way.
**When to use:** New route, new page-level feature, significant component work.
**Required context:** `CLAUDE.md` §5 (JS/React standards); exemplars: `pages/Home.jsx` (inline sub-components convention), `hooks/useApi.js`, `services/api.js`; REDESIGN_PLAN §5 (no heavy deps, tokens only).
**Workflow outline:** api-client function in `api.js` (grouped per domain) → React Query hook in `useApi.js` (query keys consistent with the family; mutations invalidate/optimistically patch) → page in `pages/` with page-local sub-components inline → route in `App.jsx` (+ legacy-redirect if renaming) → deep links carry state via params (`?deal=id`) → styling through tokens/`ui/` primitives only → verify: desktop **and** ~380 px, `vite build` clean, 0 console errors.
**Common mistakes:** fetch-in-useEffect instead of React Query; recomputing a server-computed number "just for display"; hardcoded colors bypassing tokens; a new charting/date/dep when recharts/existing utils suffice; forgetting the mobile pass (it is part of Definition of Done, not polish); missing empty states (the "Rotation healthy — show it proudly and small" school).
**Checklist:** api.js → useApi.js → page chain intact · query invalidation correct · both viewports pass · 0 console errors · deep links work · no new heavy dependency.

## S09 — `write-tests.md`

**Purpose:** What deserves tests here, and the house style for writing them.
**When to use:** Every S01–S06 flow; standalone when touching an invariant.
**Required context:** `CLAUDE.md` §10; exemplars: `tests/test_rotation_overview.py` (boundary style), `tests/test_home.py` (aggregate style), `tests/conftest.py` (fixtures).
**Workflow outline:** identify the *rule* (not the plumbing) → name boundary cases explicitly as their own tests (exactly-75% is in; empty week reads 0; race-today = 0 days; case-insensitive match) → invariant round-trips when touched (log+delete restores mileage; double-confirm is a no-op) → endpoint tests for new routes → run the full suite, record the count → removed features take their tests with them.
**Common mistakes:** testing that SQLAlchemy works; skipping the boundary that the code comment says matters; HTML-fixture tests for retailer DOMs (use dry-run endpoints instead — documented decision); letting the suite count silently drop; asserting on formatting when the rule is numeric (test seconds, not strings).
**Checklist:** rules and boundaries covered · suite green, count noted for the changelog · no scraper DOM fixtures · fixtures reused from conftest.

## S10 — `refactor-service.md`

**Purpose:** Restructure safely: seams, compatibility shims with expiries, behavior-preservation contracts.
**When to use:** Extracting logic from fat adapters; changing internals of a shared computation; retiring flagged debt.
**Required context:** `CLAUDE.md` §11 (whole section); `docs/design_decisions.md` A3, B5, D7, E4; `dependency_graph.md` §11 (the standing debt list — check your target is on it); the `activities.py` seam as the worked example.
**Workflow outline:** confirm the target's entry in design_decisions/dependency_graph (if reversing a documented decision, prep the Superseded entry) → define the observable-behavior contract ("shapes identical", "numbers unchanged") → build/locate the seam → migrate callers to the seam → swap internals → prove the contract (tests, reconciliation, or both) → if a shim was used, add it to the debt list with an expiry → docs updated in the same session.
**Common mistakes:** behavior and structure in one change; refactoring something *not* on the debt list mid-feature (drive-by rule, §11); leaving the shim off the debt list ("temporary" = immortal); breaking REST/MCP parity by refactoring only one adapter; forgetting `models/__init__` or import-convention cleanup opportunities named in dependency_graph §11.4.
**Checklist:** contract stated before, verified after · callers on the seam · debt list updated (added shim / removed finished item) · design_decisions updated if a decision changed · both API surfaces still agree.

## S11 — `background-job.md`

**Purpose:** Long-running or concurrent work under the single-process reality: locks, per-thread sessions, SSE progress.
**When to use:** Anything > a few seconds of work; anything concurrent; roadmap R4.1 groundwork.
**Required context:** `docs/architecture.md` §4 (background scrape lifecycle), §15.2; design decisions D4/D5, E5; `scrape_runner.py` + `scrape_state.py` as exemplars.
**Workflow outline:** decide sync-guarded vs background (`scrape_guard()` 409 vs `BackgroundTasks`) → acquire the relevant lock non-blocking; **the job, not the handler, releases in `finally`** → one DB session per worker thread, never shared → publish progress events to a state manager with replay-on-subscribe if a UI watches → refuse concurrency rather than queue (documented posture) → user-visible progress is part of the feature.
**Common mistakes:** handler releasing the lock (job outlives handler); sharing a session across threads; adding a scheduler/worker without reading E5 + R4.1 (the in-memory lock breaks multi-process); queuing hidden work instead of refusing visibly; SSE without replay (refresh loses the picture).
**Checklist:** lock ownership correct (release in job `finally`) · per-thread sessions · progress observable + replayable · refuses rather than stacks · single-process assumption not violated (or the design doc for changing it exists).

## S12 — `debugging.md`

**Purpose:** Where truth lives when something is wrong — the diagnostic map.
**When to use:** Any "why is this number/behavior wrong" moment, before changing code.
**Required context:** `docs/dependency_graph.md` §8 (hidden dependencies — most bugs live here); CLAUDE.md §6 traps; `TROUBLESHOOTING.md` (env-level issues).
**Workflow outline (as a decision map, not steps):**
- *Wrong number on screen* → the number is computed server-side exactly once; find the owning service (`architecture.md` §7 table); the frontend is almost never the bug.
- *Two surfaces disagree* → one of them isn't going through the shared computation — that's the bug (and a parity violation to log).
- *Run/mileage anomalies* → check the ledger invariant (§4.5) and whether a write bypassed `log_run`; the reconciliation queries from the E4 migration are reusable.
- *"Column" filter mysteriously matches nothing* → you filtered on a `ShoeRun` proxy; use `Activity` columns.
- *Chat has no tools* → the loopback: is `MCP_SERVER_URL` reaching this process? (dependency_graph §8.1).
- *Scraper silent* → `last_scraped_at` + logs per retailer; Algolia 401/403 should self-rediscover — if not, that path broke; check the retailer-status table for known-blocked.
- *Dates off by one* → UTC vs America/Toronto (145-run precedent).
- *Import/startup weirdness* → dual schema tracks: did a model change ship without a migration?
**Common mistakes:** fixing the symptom surface (frontend patch for a service bug); adding a second computation to "correct" the first; debugging the scraper against Cloudflare sites; trusting the changelog's stale reference sections (pre-R1.2) over `docs/`.
**Checklist:** root cause named in the owning layer · fix in one place · regression test if an invariant was involved · trap added to CLAUDE.md §6 if it was a new class of surprise.

## S13 — `session-wrapup.md`

**Purpose:** The end-of-session ritual that keeps the documentation system alive (R5.6's engine).
**When to use:** Every working session, last 10 minutes.
**Required context:** CLAUDE.md "Session Checklist" + §13; `docs/project_state.md` maintenance note; existing changelog entries as the format exemplar.
**Workflow outline:** suite green (record count) → build/console/viewport checks for UI work → changelog entry at top of `docs/changelog.md` (dated, `[ADDED]/[CHANGED]/[REMOVED]/[BLOCKED]`, what/why/verified-how) → `project_state.md`: snapshot date, §2 table, §9 decisions, §11 priorities; move shipped §4/§5 items to §3 → `design_decisions.md` if a decision was made/reversed → roadmap row moved if an R-item shipped → commits: one per numbered task, phase-prefixed.
**Common mistakes:** the entry says *what* but not *how verified* (test counts, reconciliations, viewport passes are the entry's spine); updating the changelog but not `project_state.md` (which decays fastest); shipping a decision reversal without a Superseded entry; batching a week of work into one commit.
**Checklist:** = CLAUDE.md Session Checklist, verbatim, plus: roadmap rows current · this-session's docs edits committed with the code.

---

## Implementation notes (for the session that builds these)

1. **Order:** S13 and S01 first (the ritual and the master flow are referenced by everything); then S03/S04 (schema safety); then S05/S06/S07 (the specialized surfaces); S02/S08/S09/S10/S11/S12 as filler between feature work.
2. Each file should be **≤ ~120 lines** — a skill that restates the docs has failed; link instead.
3. When a skill is implemented, verify its exemplar files still exist (e.g., post-R1.5 the `scraper_manager` shim disappears from S05's context; post-R2.3 `watchlist` stops being the anti-pattern example).
4. Add a one-line index of the skills to `CLAUDE.md` §3 once they exist, and record the library's creation in the changelog.
