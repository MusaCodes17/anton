# Anton — Design Decisions

**Companion to:** `docs/architecture.md`, `docs/domain_model.md`, `docs/dependency_graph.md`.
**Generated:** 2026-07-04 (post-`canonical_activities`). Sources: the codebase itself, inline decision comments, and the `docs/changelog.md` session log (formerly root `claude.md`) — several rationales below are recorded verbatim in those places; where a rationale is inferred rather than recorded, it says so.
**Purpose:** The historical record. Before reversing anything here, read its entry; if a decision is reversed, don't delete the entry — mark it superseded and say why.

**Verdict scale:** ✅ **Keep** (sound, load-bearing) · 🕐 **Keep for now** (right at current scale; revisit trigger named) · ⚠️ **Scheduled to change** (already acknowledged as transitional) · 🔁 **Superseded** (kept as history).

---

## A. Platform & Stack

### A1. Local-first, single-user, single-process
**Chosen:** One FastAPI process + SQLite file on the runner's own machine; no hosting, no tenancy, no accounts.
**Why:** Anton is a personal platform for exactly one person; operational simplicity maximizes iteration speed and the data (running history, purchases) stays on-device.
**Advantages:** Zero infra cost/ops; full-fidelity local data; refactors like `canonical_activities` can be verified against *the* production DB directly; backups are file copies.
**Trade-offs:** Concurrency and scale ceilings (see A2, F3); no access away from the machine except via LAN; "production" and "dev" are the same database.
**Verdict:** ✅ Keep the *dev posture*. **Amended 2026-07-09 (RA1.0 — D0):** serving is moving to an always-on cloud VM (Hetzner CX22 / Fly.io Shared-CPU-1x, ~$5–8 CAD/mo) so the MCP endpoint is publicly reachable over HTTPS — required because claude.ai connectors are called from Anthropic's cloud, making a Tailscale/LAN overlay insufficient for the mobile-sync goal. Local-first remains the *dev* posture; the live DB now lives on the hosted VM. The one-worker pin (D4/E8) continues to hold; the single-process assumption is not relaxed. Rejected: laptop (sleeps), always-on home box (datacenter-IP scrape risk — documented escape hatch if RA1.5 detects material degradation). See `REMOTE_ACCESS_PLAN.md` §4 for the full D0 record.

### A2. SQLite with `check_same_thread=False`, default pooling, no WAL config
**Chosen:** SQLite as the only store, accessed from request threads and scraper worker threads.
**Why:** Right-sized for one user; zero administration; trivially backed up.
**Advantages:** The whole DB is one inspectable, copyable file; Alembic batch mode handles its ALTER limitations.
**Trade-offs:** Write concurrency limits (scrape workers + requests share one writer); the safety flags lean on "one process, low contention" being true; silently invalid under multiple Uvicorn workers.
**Verdict:** 🕐 Keep for now. Revisit trigger: scheduled scraping, multi-worker serving, or any second concurrent writer pattern. A WAL pragma would be a cheap hedge before then.

### A3. Services layer with thin adapters (the 2026 refactor)
**Chosen:** Business logic extracted into `app/services/`; routers and MCP tools are adapters; one sanctioned write path per invariant (`rotation.log_run`, `DealStore`).
**Why (recorded):** Pre-refactor drift bugs — the same computation implemented differently in two places disagreeing on screen.
**Advantages:** REST/MCP parity is nearly free; invariants have single owners; the Phase-5 migration touched services and left adapters untouched.
**Trade-offs:** Older routers (`deals`, `dashboard`, `watchlist`) predate the pattern and still hold inline logic — two generations coexist; discipline is by convention, not enforced.
**Verdict:** ✅ Keep, and finish: the remaining fat routers should migrate on the schedule in `dependency_graph.md` §11.

### A4. API-first: every number computed server-side
**Chosen:** All derived figures (cost/km, retirement %, countdowns, weekly volume) computed in services; clients only render. Aggregate-per-page endpoints (`/home`, `/watchlist`).
**Why (recorded):** A future native mobile client must show identical numbers without reimplementing math; embedded as a first-class requirement.
**Advantages:** Web, MCP, assistant, and future mobile cannot disagree; frontends stay thin.
**Trade-offs:** Chattier server work per request; aggregate endpoints do more in one call (accepted deliberately at personal scale).
**Verdict:** ✅ Keep. This is the platform's most valuable standing discipline.

### A5. React 18 + Vite, JSX without TypeScript
**Chosen:** Plain JSX SPA with React Query, Tailwind/shadcn-style components.
**Why (inferred):** Solo-developer velocity; the API-first rule (A4) moves correctness-critical logic server-side, lowering the payoff of frontend typing.
**Advantages:** Fast iteration; no build-type friction; React Query centralizes server state.
**Trade-offs:** The API contract exists only as matching string literals and shape knowledge on both sides; refactors of response shapes are grep-verified, not compiler-verified.
**Verdict:** 🕐 Keep for now. Revisit trigger: the mobile client — a second consumer is the moment a generated/typed API contract starts paying for itself.

### A6. Alembic (batch mode) **plus** startup `create_all`
**Chosen:** Alembic owns migrations (`render_as_batch` for SQLite), while `init_db()` still runs `create_all` at boot; pre-Alembic scripts retained in `legacy_migrations/`.
**Why:** `create_all` predates Alembic and was kept as a convenience (fresh setups work with zero steps); legacy scripts kept as history.
**Advantages:** Fresh clones boot instantly; migration history exists and is now high quality (D1).
**Trade-offs:** Two authorities over the schema — a model edit without a migration "works" on fresh DBs and diverges on real ones; ambiguity about the canonical path.
**Verdict:** 🔁 **Superseded — executed r2: 2026-07-07** (R2.2). Alembic is now the sole schema authority: startup runs `alembic upgrade head` (`database.run_migrations()`) instead of `create_all`, which now lives only in the test fixtures. The formerly-empty baseline revision (`cf1eccba0a79`) recreates the exact pre-Alembic schema, so a fresh DB builds entirely from Alembic (verified table-for-table against the models; round-trips to base). `legacy_migrations/` was **deleted** (git history is the archive), and the live DB + backups moved to `~/anton-data/` (backups under `~/anton-data/backups/`, dated-backup convention). See changelog 2026-07-07.

### A7. The pinned dependency triangle
**Chosen:** FastAPI 0.109 + Starlette 0.35.1 + sse-starlette 1.8.2 pinned together, with the reason documented in `requirements.txt`.
**Why (recorded):** `mcp[cli]` 1.28.0's transitive requirements conflict with newer/older combinations; this triple is the verified-working resolution.
**Advantages:** Reproducible environment; the *reason* traveling with the pin prevents well-meaning upgrades from breaking MCP transport.
**Trade-offs:** Frozen off the FastAPI/Starlette upgrade path until the MCP SDK moves; security patches to pinned versions need manual watching.
**Verdict:** ✅ Keep the practice (pin + documented reason); revisit the specific pins whenever `mcp` is upgraded.

---

## B. Domain Modeling

### B1. Tracked Shoe and Owned Shoe are separate entities with **no relationship**
**Chosen:** `shoes` (watchlist) and `owned_shoes` (rotation) share no FK; buying is not modeled as a transition.
**Why (recorded in code):** Wanting and owning are independent facts with independent lifecycles.
**Advantages:** Each domain evolves freely; deleting watchlist interest can't damage run history; no forced purchase workflow.
**Trade-offs:** The domains can only meet heuristically (B3); "I bought the shoe I was tracking" is untracked knowledge.
**Verdict:** ✅ Keep. The single most load-bearing *absence* in the schema — see `domain_model.md` §5.1 before ever "fixing" it.

### B2. Size-less shoe tracking
**Chosen:** A tracked shoe is brand+model across **all** sizes.
**Why (recorded):** Restricting to one size hides deals whenever that size is out of stock; size availability is captured per-observation instead.
**Advantages:** Far higher deal recall; simpler matching.
**Trade-offs:** A deal may exist only in unusable sizes — triage moves to the human reading `sizes_available`.
**Verdict:** ✅ Keep. (A "my sizes" filter would be a *view* refinement, not a model change.)

### B3. Cross-domain bridge via `shoe_type` strings, not foreign keys
**Chosen:** "Replacement deals" for a wearing-out shoe = active deals on tracked shoes with the same free-string `shoe_type`.
**Why:** Preserves B1's independence while still connecting retirement to shopping; honest about being a heuristic (labeled so in code).
**Advantages:** Domains stay decoupled; zero migration cost; degrades silently rather than erroring.
**Trade-offs:** Stringly-typed — a typo yields zero hints with no signal; vocabulary duplicated in three places (backend, frontend `shoeTypes.js`, MCP docstrings).
**Verdict:** 🕐 Keep the bridge; formalize the vocabulary (controlled list served by the backend — architecture.md §16.5). The *no-FK* principle stands; the *free-string* part is the debt. The current value set is enumerated in `domain_model.md` §4.3 (as-of 2026-07-06, mirrored in `frontend/src/lib/shoeTypes.js`) — the canonical list until R2.4 formalizes it.

### B4. Canonical `activities` table; `shoe_runs` reduced to attribution (Phase 5)
**Chosen:** One row per physical run regardless of source; shoe attribution is a separate row; the old `strava_activities`/data-bearing-`shoe_runs` split and its reconciliation machinery removed.
**Why (recorded):** The two-store union required permanent dedup-by-link logic; the seam (`activities.py`) was explicitly designed so this swap could happen invisibly — and did.
**Advantages:** "Never double-count" enforced structurally; one pace representation (seconds/km); COROS/manual/archive runs are uniform; backfill service deleted outright.
**Trade-offs:** See B5; also `strava_gear_mappings` becomes dormant history.
**Verdict:** ✅ Keep. Also a *process* precedent: reversible migration, pre/post reconciliation, backup, suite green — the bar for future structural changes.

### B5. Compatibility via `ShoeRun` property proxies instead of renaming/reshaping
**Chosen:** `shoe_runs` kept its name and its old field names as read-only properties resolving through the joined Activity, so every response shape and consumer survived Phase 5 unchanged.
**Why (recorded):** Zero frontend/MCP churn during a deep storage restructure; continuity of meaning over naming purity.
**Advantages:** The migration shipped in one day with no consumer changes; API stability honored.
**Trade-offs:** Hidden N+1 on un-eager-loaded run loops; proxied attributes silently unusable in `filter()`; pace formatting duplicated into the ORM class.
**Verdict:** 🕐 Keep **as a bridge, not a permanent API** (architecture.md §16.4): eager-load at list seams now, migrate readers over time, shrink the proxy surface.

### B6. Mileage as a maintained counter, not a derived sum
**Chosen:** `current_mileage = starting_mileage + Σ attributed distances`, updated on every write/delete, never recomputed on read.
**Why (recorded):** `starting_mileage` honors pre-tracking wear; displayed totals are a promise (Phase 5 shipped under an explicit "counters untouched" guarantee); reads stay trivial.
**Advantages:** Cheap reads; totals stable through storage restructures; the invariant is testable.
**Trade-offs:** A ledger can drift if any writer bypasses the sanctioned path — which is exactly why B7 exists; reconciliation checks are manual (the migration ran one).
**Verdict:** ✅ Keep, paired inseparably with B7.

### B7. One sanctioned write path for runs (`rotation.log_run`)
**Chosen:** Every run — manual, COROS, (historically) backfill — enters through one function that creates the Activity, the attribution, updates the ledger, and detects checkpoints; escape hatches (`increment_mileage`, `commit`) exist for batch callers rather than parallel paths.
**Why (recorded):** The counter invariant (B6) is only defensible with a single writer.
**Advantages:** Whole classes of drift bugs impossible; checkpoint detection can't be forgotten on a new ingestion path.
**Trade-offs:** The function accumulates flags as callers diversify; discipline is conventional.
**Verdict:** ✅ Keep. This is the domain's strongest guarantee.

### B8. Append-only price history; deals as qualified snapshots
**Chosen:** `price_records` never edited/deleted; a `Deal` snapshots the savings that qualified it (refreshed on change) rather than joining live. As of B9-v2 the snapshot is measured against MSRP; `target_price` is retained on the row only as a reference threshold.
**Why:** Price *history* is the product (best-ever, trends); the snapshot records *why this qualified* at detection.
**Advantages:** Honest analytics; deal rows are self-explanatory historical records.
**Trade-offs:** Unbounded (slow) growth; the denormalized savings are a second copy requiring the refresh rule.
**Verdict:** ✅ Keep. Growth is glacial at personal scale.

### B9. Deal qualification requires *both* a genuine markdown *and* target hit
**Chosen:** `original_price > price` **and** `price ≤ current target`; targets read fresh each evaluation; `msrp` stored separately from `target_price`.
**Why (recorded):** "At my number but full price" isn't an opportunity; "big markdown, still too expensive" isn't either; and list-price vs willingness-to-pay must never be conflated.
**Advantages:** High-precision alerts — the deal feed means something; target edits take effect immediately.
**Trade-offs:** Misses genuine price drops the retailer doesn't flag as sales (rare on these platforms).
**Verdict:** 🔁 **Superseded by B9-v2 (2026-07-06).**

### B9-v2. Deal qualification is *price below MSRP*; target_price is an optional threshold
**Chosen:** a deal is any `price < shoe.msrp` (MSRP read fresh each evaluation); savings % is measured against MSRP (`(msrp - price)/msrp`). The retailer's own compare-at/markdown flag is no longer consulted, and `target_price` no longer affects qualification or savings — it is demoted to an optional personal "ping me at" threshold (both `target_price` columns made nullable).
**Why (recorded):** The runner wants a single, self-evident meaning of "on sale" — below list price — and a savings % anchored to a real reference (MSRP) rather than a private willingness-to-pay number. MSRP was populated on every active shoe first, so nothing became silently un-dealable.
**Advantages:** One honest number everywhere ("% off retail"); no dependence on retailers correctly flagging compare-at prices; higher recall.
**Trade-offs:** Lower precision than B9 — a retailer that habitually prices below MSRP will always read as "on sale"; shoes without an MSRP produce no deals at all. Reverses B9's markdown-required guard (e.g. the Adios Pro 4 full-price-at-target false positive is now handled by MSRP instead).
**Verdict:** ✅ Keep (current). Revisit if below-MSRP-always retailers make the feed noisy — a per-retailer floor or an optional markdown-required flag would be the escape hatch.

### B10. Orphan retirement with the non-empty-search guard
**Chosen:** Deals whose URLs vanish from a *successful, non-empty* search are deactivated; empty/failed scrapes retire nothing.
**Why (recorded):** Renamed/delisted products left zombie deals; but a transient outage must never mass-extinguish the feed.
**Advantages:** Self-cleaning feed with a safety interlock.
**Trade-offs:** A retailer legitimately dropping to zero matching products delays cleanup until a manual pass.
**Verdict:** ✅ Keep.

### B11. The frozen archive rule
**Chosen:** `source='strava'` activities are the immutable 8-year record: deleting a run attribution deletes the underlying activity *except* archive rows, which merely un-attribute.
**Why (recorded):** The bulk export is irreplaceable history; attribution is an opinion, the run is a fact.
**Advantages:** History can be re-curated without risk of destruction.
**Trade-offs:** Asymmetric delete semantics that every future writer must know (documented in `domain_model.md` §4.8).
**Verdict:** ✅ Keep.

### B12. Journal notes: timestamped, mileage-anchored, append-only
**Chosen:** `shoe_notes` rows with server-stamped `mileage_at_note` and `triggered_by`, replacing an earlier single free-text column.
**Why (recorded):** "How it felt at 400 km" is only meaningful anchored to 400 km; checkpoint prompts (every 100 km) create the anchors.
**Advantages:** A genuine wear diary; the raw material MCP's review-drafting consumes.
**Trade-offs:** No edit story (append-only by convention).
**Verdict:** ✅ Keep.

### B13. Derived values never stored (races, cost/km, pipeline %)
**Chosen:** Countdowns, required paces, cost/km, retirement % computed at read time, attached at the boundary.
**Why (recorded on `planned_races`):** Time-relative values stored are values guaranteed stale.
**Advantages:** Can't go stale; one computation shared by REST and MCP.
**Trade-offs:** Recomputed per request (trivial at scale). The two stored exceptions are deliberate: the mileage ledger (B6) and the deal's qualifying-savings snapshot (MSRP-based since B9-v2; see B8).
**Verdict:** ✅ Keep.

### B14. America/Toronto as the calendar
**Chosen:** Run dates are local dates in a hard-coded home timezone; UTC and local timestamps stored under explicit names.
**Why (recorded):** 145 evening runs in the Strava export shift calendar days if UTC dates are used naively.
**Advantages:** Dates match lived experience; dedup-by-date works.
**Trade-offs:** Hard-coded home zone (travel racing logs to Toronto dates); acceptable and known.
**Verdict:** ✅ Keep. Revisit only if multi-timezone life becomes real.

### B15. Activity-tag controlled vocabulary (R2.7 T1)
**Chosen:** `activity_tag` is a small closed set (Easy · Long Run · Recovery · Tempo · Intervals · Track · Workout · Trail · Parkrun · Race) owned by the backend in one pure module (`app/utils/activity_tags.py`) and served to the frontend (`GET /api/activities/tags`), not a free-text string.
**Why:** the tag governs PB eligibility (B16), race promotion (T6), and the weekly-summary agent (R3.1) — a load-bearing set where a typo would fail silently. One served source avoids the three-copies problem that `shoe_type` still has (R2.4 will mirror this pattern).
**Advantages:** typed/validated at the MCP boundary; one edit point; frontend never drifts.
**Trade-offs:** growing the list is a schema-grade change (a test pins the exact set), deliberately — tags must not proliferate casually.
**Verdict:** ✅ Keep. This is the reference pattern for R2.4's `shoe_type` vocabulary.

### B16. PB eligibility: tag exclusion + elapsed-time guard (R2.7 T3)
**Chosen:** personal bests exclude Intervals/Track tags always, include Race/Parkrun always, include other run tags, and for untagged runs apply an elapsed-time guard (`elapsed > 1.5 × moving` ⇒ stop-heavy ⇒ excluded). The dropped count + reason ride along in the response.
**Why:** the PB algorithm bands *whole-activity* times, so a stop-heavy interval session could fake a record at its rep distance. The tag is the clean intentional signal; the ratio is the honest fallback for the untagged 8-year archive.
**Advantages:** removes false records without hiding legitimate fast efforts; transparent (the UI can prompt tagging).
**Trade-offs:** untagged history relies on a heuristic ratio (1.5× is a judgment call); tagging improves accuracy over time. These are still whole-activity bests, not segment PBs (unchanged).
**Verdict:** 🕐 Keep for now. Revisit the ratio if it proves too tight/loose once more history is tagged.

---

## C. AI Layer

### C1. MCP as the single AI substrate; the assistant is a client of its own server
**Chosen:** All AI capability defined once as MCP tools/resources/prompts; Son of Anton connects as an MCP client to the app's own `/mcp` over loopback and discovers tools dynamically (`list_tools`, not Python imports).
**Why (recorded):** One tool registry for Claude Desktop *and* the embedded chat; a new `@mcp.tool()` becomes a chat capability with zero further wiring; an earlier direct-import coupling was deliberately removed in favor of discovery.
**Advantages:** Perfect capability parity across AI surfaces; the assistant can never do what the platform can't; dogfoods the MCP server continuously.
**Trade-offs:** A runtime self-dependency over TCP (`MCP_SERVER_URL` must reach the app itself — the hidden loop in `dependency_graph.md` §7.3); per-conversation connection overhead.
**Verdict:** ✅ Keep the architecture; make the loopback explicit or in-process per architecture.md §16 / dependency_graph.md §11.7.

### C2. Multi-provider chat via strategy pattern, routed by model-name prefix
**Chosen:** Anthropic/OpenAI/Gemini providers implementing one streaming agentic-loop contract; availability driven by which API keys exist.
**Why:** Freedom to compare/switch models; key-presence-as-feature-flag keeps config zero-touch.
**Advantages:** Model experimentation is a dropdown; no provider lock-in.
**Trade-offs:** The loop is implemented three times (~100 lines each) and must change in triplicate; model catalogs hard-coded in the router drift from prefix routing in the service.
**Verdict:** 🕐 Keep the strategy; consolidate the catalog (single source) and consider whether three loops still pay rent at next protocol change.

### C3. Resources return markdown **with** embedded JSON
**Chosen:** Every MCP resource renders human-readable markdown plus a machine-parseable JSON payload in one body.
**Why:** The same resource serves a human skimming Claude Desktop and a model needing structured data.
**Advantages:** No dual-endpoint maintenance; resources are self-documenting.
**Trade-offs:** Bigger payloads; two renderings to keep consistent within one function.
**Verdict:** ✅ Keep.

### C4. Context priming + trust rules in the system prompt
**Chosen:** Rotation and active-deals resources are pre-read into the chat system prompt as "live context," with explicit rules for when to trust it vs. re-query, plus behavioral guardrails (verify-before-claiming, check-before-adding).
**Why (recorded):** Cuts redundant tool calls for the two most-referenced datasets while preventing stale-context assertions.
**Advantages:** Faster, cheaper conversations; fewer hallucinated states.
**Trade-offs:** Prompt-encoded policy is invisible to type systems and easy to forget when resources change shape.
**Verdict:** ✅ Keep.

### C5. `MAX_AGENTIC_TURNS = 25` + isolated-task/queue streaming
**Chosen:** A hard loop cap independent of model behavior; the agentic loop runs in one isolated asyncio task communicating over a queue so anyio cancel scopes never cross the SSE generator.
**Why (recorded):** Loop termination must be a *server* guarantee; a real class of cancel-scope bugs was confined this way.
**Advantages:** No runaway loops or hung streams regardless of model/provider behavior.
**Trade-offs:** Very long legitimate tool chains truncate at 25 (unobserved in practice).
**Verdict:** ✅ Keep.

### C6. COROS sync as a **client-side agent prompt**, not a backend integration
**Chosen:** The `sync_coros_runs` MCP prompt instructs Claude Desktop to read the *external* COROS MCP connector, dedup, propose, wait for confirmation, then write via this server's tools. A prior direct backend integration of the COROS MCP was **removed**.
**Why (recorded):** COROS blocks Open-API keys for individuals, and the COROS MCP's OAuth is desktop-client-managed — un-drivable from backend code. The server-side `coros_client` path remains, dormant, behind env credentials.
**Advantages:** Works today with zero credential access; the protocol is versioned prose, editable without deploys; human confirmation is built into the script.
**Trade-offs:** Depends on a third party's tool names/schemas (a rename breaks silently); requires Claude Desktop in the loop; two parallel sync paths exist (one dormant).
**Verdict:** 🕐 Keep — it's the pragmatic optimum under COROS's constraints. 🔁 The removed direct integration stays superseded unless COROS opens API keys, which would revive the dormant server path.

### C7. MCP sampling for review drafting
**Chosen:** `draft_shoe_review` asks the *connected client's* LLM (server→client `create_message`) to draft from journal notes, degrading gracefully when unsupported.
**Why:** The client already has a paid, user-chosen model; the server shouldn't spend its own tokens or hardcode a model for a generative nicety.
**Advantages:** Zero server-side LLM cost/config; exercises the rarest MCP primitive.
**Trade-offs:** Capability varies by client; output quality is client-dependent.
**Verdict:** ✅ Keep.

### C8. Chat history in browser localStorage
**Chosen:** Conversations (cap 50) and checkpoint-prompt state live only client-side; the backend is stateless per chat request.
**Why (inferred):** Simplest possible persistence during the assistant's build-out; avoided premature schema for conversations.
**Advantages:** Zero backend surface; privacy-by-locality.
**Trade-offs:** Device-bound memory at odds with the multi-client trajectory (A4); quota-trimming silently discards history; invisible to future server-side agents.
**Verdict:** 🔁 **Superseded by C10 (R2.6, 2026-07-08).** Conversations and checkpoint-prompt state now live in the backend (`chat_conversations`, `checkpoint_prompts`); localStorage is no longer read (existing local data was abandoned, not migrated — start-fresh, confirmed with the runner). This was the last ⚠️ scheduled-to-change decision.

### C10. Server-side chat & memory persistence (JSON columns, start-fresh)
**Chosen (R2.6, 2026-07-08):** Son of Anton conversations and the 100 km checkpoint-prompt state persist in two backend tables (`chat_conversations`, `checkpoint_prompts`, migration `e1f2a3b4c5d6`). The streaming endpoint (`POST /chat/message`) stays stateless per request; a separate CRUD surface (`GET/PUT/DELETE /chat/conversations[/{id}]`, `GET/POST /checkpoint-prompts`) does persistence. The client PUTs the full conversation on stream-end (whole-conversation replace, mirroring the old localStorage save); the server caps the store at 50, trimming oldest-updated.
**Why:** Device-bound memory contradicted the API-first multi-client principle (A4); server-side agents (R3) need shared context; R2.1 auth (E7) made the chat endpoints no longer anonymous, which was the precondition.
**Key sub-decisions:**
- **Message arrays as JSON columns, not a normalized messages table** — `display_messages` carries pure UI concerns (tool-call events, pill previews, dividers) that don't relationally model well; at single-user scale (cap 50) normalizing is speculative infra (CLAUDE.md §2.5). Labelled in the model docstring.
- **`chat_conversations.id` is the client-generated UUID** — preserves the frontend's in-memory-first / persist-on-first-message flow (an unsaved conversation isn't written until its first message) and avoids remounting the keyed chat area mid-stream.
- **Start-fresh** — existing localStorage conversations are *not* migrated up; the server starts empty (runner's call). Old local data is simply no longer read.
- **MCP exposure deferred to R3** — R2.6's only consumer is the SPA; the agent-facing read surface for chat history is R3 work.
**Advantages:** Memory is device-independent; history survives a browser clear; server-side agents can read it later.
**Trade-offs:** No per-user scoping (single-user, no auth identity — deliberate); the whole-conversation PUT on stream-end re-sends the full arrays (fine at personal scale). In-process still (single-process assumption, D4).
**Verdict:** ✅ Keep.

### C9. Human confirmation gates all AI/synced writes
**Chosen:** No externally-sourced run is auto-logged; assistants present suggestions (pace-primary, distance-secondary, active shoes, low-mileage tiebreak) and wait. Retirement is advised, never enacted.
**Why (recorded everywhere — prompt text, service docstrings, memories):** The runner is the tiebreaker; automation prepares, the human disposes.
**Advantages:** Trust in the data stays absolute; wrong suggestions are cheap.
**Trade-offs:** Sync is never fully hands-free — by design.
**Verdict:** ✅ Keep. This is Anton's automation posture, not a missing feature.

---

## D. Scraping

### D1. Platform base classes + bespoke subclasses + DB-driven dynamic registry
**Chosen:** Generic `AlgoliaScraper`/`ShopifyScraper` bases; eight named subclasses for quirks; unknown retailers get a dynamic scraper built from `Retailer.platform` + `scraper_config`, with platform auto-detected at creation.
**Why:** Retailer frontends are the highest-churn boundary; shared mechanics belong in one place, quirks in named files, and adding a mainstream retailer shouldn't require code.
**Advantages:** New Shopify/Algolia retailers are a DB row; fixes to shared logic (price parsing, stock phrases) propagate everywhere.
**Trade-offs:** Bespoke subclasses accumulate; `custom` platforms (En Route's headless Astro) always need real code; two retailers remain unscrapable behind Cloudflare.
**Verdict:** ✅ Keep.

### D2. Algolia credential self-rediscovery
**Chosen:** On 401/403, headless Playwright drives the retailer's own search box and intercepts `*.algolia.net` XHR to recover fresh app-id/key/index (stripping sort-replica suffixes).
**Why (recorded):** Retailers rotate public search credentials; manual re-harvesting was toil.
**Advantages:** Self-healing against the most common Algolia breakage.
**Trade-offs:** Playwright as a hard operational dependency; rediscovery itself breaks if the search UI changes.
**Verdict:** ✅ Keep.

### D3. Politeness by construction; no bot-evasion arms race
**Chosen:** 2–3 s sleeps per request, sequential shoes within a retailer, configurable honest User-Agent; an explicit decision **against** paid Cloudflare-bypass services (two retailers simply marked unreachable).
**Why (recorded):** Personal-scale scraping should be a good citizen; the arms race costs money and ethics for marginal coverage.
**Advantages:** Low ban risk; clean conscience; predictable load.
**Trade-offs:** Full scrapes take 20–30+ minutes; two retailers' prices are invisible.
**Verdict:** ✅ Keep.

### D4. One process-wide scrape lock; refuse rather than queue
**Chosen:** A single `threading.Lock` guards *every* scrape entry point; concurrent triggers get 409/`started:false`, never a queue. The background job owns release in `finally`.
**Why (recorded):** Stacked triggers once meant "scraping forever"; refusing is legible, queuing hides cost.
**Advantages:** At most one scrape exists; trivially reasoned about.
**Trade-offs:** In-memory ⇒ single-process assumption (invalid under multi-worker); coarse — a one-shoe scrape blocks everything.
**Verdict:** 🕐 Keep for now. Revisit trigger: scheduled scraping or any multi-process move ⇒ persist coordination (architecture.md §16.6).

### D5. Background scrape = per-retailer threads over the same primitive; SSE with full-history replay
**Chosen:** `/scrape/all` runs retailers concurrently (one thread + one DB session each; shoes sequential within), publishing progress to an in-memory pub/sub whose late subscribers receive the full event history. Documented as an *additional* path over the same per-(shoe, retailer) unit, not a replacement.
**Why (recorded):** Wall-clock relief without touching per-retailer politeness; replay so a refreshed browser doesn't lose the picture.
**Advantages:** ~8× wall-clock; progress UX survives reconnects; one scraping primitive.
**Trade-offs:** In-memory state shares D4's single-process assumption; no persisted scrape history (observability gap flagged in architecture.md §15.8).
**Verdict:** ✅ Keep the shape. The persistence gap is **closed by R2.5** (D8) — durable per-retailer runs now live in `scrape_runs`, alongside the transient SSE state, not replacing it.

### D6. Kids filtering and promo heuristics centralized in `BaseScraper`
**Chosen:** Junior/kids exclusion applied once in `search_products_filtered`; promo codes found by regex pairing codes with nearby "% off" text; **manual promo codes never overwritten by scraped ones**.
**Why:** Every subclass inherits hygiene it can't forget; human-entered knowledge outranks a crawl.
**Advantages:** Uniform catalog cleanliness; safe manual curation.
**Trade-offs:** Regex promo detection has inherent precision limits (accepted).
**Verdict:** ✅ Keep.

### D7. `scraper_manager.py` retained as a compat shim post-refactor
**Chosen:** The monolith's names re-exported from a shim while orchestrator/registry/lock/deal_store became real modules; all four consumers still import the shim.
**Why (recorded in the shim itself):** Decompose without touching every call site in the same change.
**Advantages:** The refactor landed safely in one session.
**Trade-offs:** Real module boundaries invisible at call sites; the "temporary" is aging.
**Verdict:** 🔁 **Superseded — shim deleted r1: 2026-07-07** (R1.5b, debt sweep #1). All five consumers (`routers/scraping`, `routers/shoes`, `mcp_server`, `scrape_runner`, `scrapers/__init__`) now import `ScrapeOrchestrator` / `lock` / `registry` directly; the misleading `ScraperManager` alias is gone. See changelog 2026-07-07.

### D8. Durable scrape observability in `scrape_runs`, written by one orchestrator path (R2.5)
**Chosen:** One `scrape_runs` row per retailer per full-catalog scrape attempt (status/counts/error), written **only** by `ScrapeOrchestrator.scrape_retailer` — stamped `running` and committed up front, finalized to `success`/`error`. Health (`ok`/`warning`/`error`/`unknown`) is derived at read time by `services/scrape_history`, never stored. The `warning` verdict (finished clean, zero products) is the "quietly broken" signal that no error status carries.
**Why (recorded):** "Is Altitude quietly broken?" was log archaeology; D5's SSE state is transient (current job only). R4.1 (scheduling) / R4.5 (watchdog) need a durable place to record per-retailer outcomes, and this is it.
**On the single-process lock (the decision R2.5 was said to "force"):** R2.5 records history but deliberately **does not** change D4's in-memory lock. Observability is orthogonal to coordination: a durable `scrape_runs` table does not require durable *locking*. The single-process lock stays as-is (🕐); the forcing function for replacing it is R4.1's *scheduled/unattended* execution, not R2.5's *record-keeping*. Naming it here so a future session doesn't re-open D4 prematurely.
**Advantages:** Health is a query; up-front `running` commit makes in-flight/crashed scrapes visible (verified live); one write path keeps the invariant (CLAUDE.md §2.2); cascade-deleted with its retailer (disposable deals-domain telemetry, §2.6).
**Trade-offs:** Only the two full-catalog flows (background `/scrape/all`, synchronous `/scrape/retailer/{id}`) emit runs so far; the shoe-major `scrape_all_shoes` / single-shoe path (MCP `trigger_scrape` sans shoe_id) doesn't yet — deliberate, its grain is wrong for a per-retailer run.
**Verdict:** ✅ Keep. Revisit when R4.1 adds `trigger="scheduled"` and a watchdog reads the trend.

---

## E. Operations & Process

### E1. No authentication anywhere (deferred, not forgotten)
**Chosen:** REST, MCP, and the chat LLM-proxy are all open; trust = network posture (with a `0.0.0.0` default bind). The backlog explicitly holds "security pass: API auth, rate limiting, MCP endpoint auth."
**Why:** Single user on a trusted machine; auth earlier would have taxed every iteration of every surface.
**Advantages:** Frictionless development of three parallel interfaces.
**Trade-offs:** Anyone reaching port 8000 can mutate data and spend LLM credits; every exposure-increasing feature is gated on fixing this.
**Verdict:** 🔁 **Superseded by E7 (R2.1 bearer-token auth, 2026-07-07).** The security pass shipped: a shared bearer token now gates `/api/*` and `/mcp`, the default bind moved to `127.0.0.1`, and the loopback client sends the token. The `SECURITY_PASS_PLAN.md` threat model, alternatives, and rollout are the historical record. See E7 and changelog 2026-07-07.

### E2. Live DB + manual `.bak` copies in the working tree; `export.py` as code-as-backup
**Chosen:** `shoe_deals.db` and five point-in-time `.bak*` siblings live beside the code; separately, `/api/export` regenerates `seed_data.py` from live retailers/shoes so a fresh DB can be reseeded to current curation.
**Why:** File-copy backups are the honest SQLite recovery story at this scale; the seed export solved recorded drift (UI-added shoes lost on reset).
**Advantages:** Every risky migration had a named restore point (`.bak-pre-activities`); curation survives DB resets via version-controlled code.
**Trade-offs:** Backups jumbled with source; "which file is canonical" ambiguity; large binaries near git.
**Verdict:** 🕐 Keep the *practices* (pre-migration backups, seed export); relocate the files out of the tree with a naming convention (architecture.md §16.2).

### E3. The session changelog (`docs/changelog.md`, formerly root `claude.md`) as decision log + §-referenced planning docs
**Chosen:** A living changelog file (now `docs/changelog.md`; originally at the root as `claude.md`), with code comments citing planning-doc sections (`§3 Phase-5`, `P3.4`) as an internal citation system.
**Why:** Solo, AI-assisted development across many sessions needs durable institutional memory more than most teams do.
**Advantages:** Rationales are recoverable (this document is largely built from them); every AI session starts with real context; plans and code cross-reference.
**Trade-offs:** The log's *overview* sections drift from reality between sweeps; discipline is manual.
**Verdict:** ✅ Keep — arguably the project's defining practice. The `docs/` suite generated by this workflow is its extension, not its replacement.

### E4. Migration discipline as demonstrated by `canonical_activities`
**Chosen (as precedent):** Structural migrations are reversible, preceded by an explicit backup, verified by pre/post reconciliation against live data (counts, totals, zero drift), and land with the suite green and UI spot-checks recorded.
**Why:** The live DB is the only DB (A1); there is no staging to save you.
**Advantages:** Deep restructures are survivable and provably lossless.
**Trade-offs:** Costly ceremony — appropriate exactly because of A1.
**Verdict:** ✅ Keep as the standing bar for any migration that moves data, not just adds columns.

### E5. APScheduler declared, unused
**Chosen (implicitly):** The dependency was added ahead of a scheduled-scraping feature that hasn't been designed; all scraping remains manual-trigger.
**Why (inferred):** Anticipatory install.
**Advantages:** None yet.
**Trade-offs:** A dependency without an architecture invites drive-by wiring that would collide with D4's lock assumptions.
**Verdict:** 🔁 **Superseded — dropped r1: 2026-07-07** (R1.6). Removed from `requirements.txt`; a scheduling note was added to `scrapers/lock.py`. Reinstate only when scheduled scraping (roadmap R4.1) has a real design — persisted job state + DB-level coordination replacing the in-memory lock. See changelog 2026-07-07.

### E6. The rebrand carries old names in code
**Chosen:** The platform is **Anton** (assistant: **Son of Anton**) while the repo, API title, and DB filename retain "running-shoe-deals" / "Running Shoe Deal Finder."
**Why:** Renaming repos/paths mid-flight is churn with near-zero user value for a single user.
**Advantages:** Zero breakage; identity lives in the UI and docs where it matters.
**Trade-offs:** Mild permanent confusion for newcomers (including AI sessions) — mitigated by the glossary (`domain_model.md` §7.1).
**Verdict:** ✅ Keep until some other forcing event (e.g., repo migration) makes the rename free.

### E7. Single shared bearer token for all surfaces (R2.1 — supersedes E1)
**Chosen:** One random secret (`ANTON_SECRET` in `.env`); every request to `/api/*` and the mounted `/mcp` must carry `Authorization: Bearer <ANTON_SECRET>` (constant-time compare in one app-wide ASGI middleware), with a tiny public allowlist (`/`, `/health`, `/api/health`) and OPTIONS preflight exempt. Default bind moved to `127.0.0.1` (`API_HOST=0.0.0.0` is the explicit, now-safe LAN opt-in); the app fails fast if the secret is unset. All three consumers send the token: the SPA (baked-in `VITE_ANTON_SECRET`, on the axios interceptor **and** the raw chat `fetch`/scrape SSE paths), Claude Desktop (`mcp-remote --header`), and the loopback client (Son of Anton, injected at connect time — scoped so the secret never reaches an external MCP server).
**Why:** Zero UX friction for one user, uniform across all three consumers, symmetric-secret verification with no cert/JWT lifecycle. The threat model is an untrusted process/person on the same LAN — not the internet, not local root. Full rationale and rejected alternatives (per-client keys, cookies+login, mTLS, OAuth, reverse-proxy-only): `SECURITY_PASS_PLAN.md` §3 + §8.
**Advantages:** No anonymous mutations, no anonymous LLM spend; the precondition for every exposure-increasing R3–R5 feature. Middleware is pure-ASGI so SSE and the `/mcp` stream pass through untouched.
**Trade-offs:** One static secret in cleartext on the trusted LAN (accepted — §1); rotation is a deliberate `.env`-edit + restart, not hot-rotation (§8 Q3); no rate limiting yet (separate R2 item, §6); `/docs`/`/openapi.json` now require the token too.
**Verdict:** 🔁 **Superseded by E9 (RA1.1 — 2026-07-09).** The shared-secret model was sound for the trusted LAN but incompatible with the internet threat model (no per-client revocation; `ANTON_SECRET` was baked into every SPA bundle ever built). The ASGI middleware shape (`BearerAuthMiddleware`, pure-ASGI, constant-time compare, empty 401) is **kept** — E9 changes what is compared, not how. Historical rationale: `SECURITY_PASS_PLAN.md` §3 + §8.

### E8. In-process token-bucket rate limit on `POST /api/chat/message` (R2 — completes the R2.1 spend story)
**Chosen:** A token-bucket limiter (`services/rate_limit.py`) capping the request rate on the chat endpoint, keyed by client IP, enforced by a FastAPI dependency that returns **429 + `Retry-After`** before the SSE stream starts. State is in-memory; default 20 req/min with a burst of 20, tunable via `CHAT_RATE_LIMIT_PER_MINUTE` / `CHAT_RATE_LIMIT_BURST`.
**Why:** E7/R2.1 stopped *anonymous* LLM spend but left an authenticated client free to loop and burn paid credits (SECURITY_PASS_PLAN §6, the explicitly-deferred item). Under the single-user LAN threat model the realistic adversary is a *bug* (retry storm, runaway agent), not a hostile flood — so the goal is bounding accidental spend, not hardening against DoS. A token bucket allows normal bursty human use while hard-capping sustained rate.
**Advantages:** Closes the last R2.1-adjacent gap; no new dependency; deterministic to test (injectable clock); pure request-time dependency so the SSE stream is untouched.
**Trade-offs:** In-process only — like the scrape lock (D4/E5), it assumes one worker; a second process would each keep its own bucket (labelled, not silent; DB-level coordination deferred to whenever a scheduler/worker arrives, R4.1). Per-IP keying means all requests behind one NAT share a bucket, and the bucket dict is unevicted (bounded by the owner's device count at single-user scale). Not a security boundary — auth (E9) is; this is a spend guardrail.
**Verdict:** 🕐 Keep for now. Revisit (shared store, per-token quotas, or eviction) only if a second worker or remote/multi-client access appears (R5.2).

### E9. Named per-client bearer tokens + OAuth 2.1 connector auth (RA1.1 + RA1.1b — supersedes E7)

**RA1.1 (2026-07-09):** `ANTON_TOKENS="name:token,..."` replaces the single `ANTON_SECRET`. The ASGI middleware (`app/middleware/auth.py`) reads the map at `__init__` time, constant-time OR-compares (`result |= secrets.compare_digest(presented, token)`) every entry without short-circuiting, and forwards unchanged — pure ASGI so SSE + MCP streaming pass through untouched. `get_named_token(name)` re-reads `ANTON_TOKENS` on each call (not cached) for `chat_service`. The capability-URL bypass (`ANTON_CONNECTOR_TOKEN`) shipped simultaneously as a fallback path but was explicitly held dark pending the RA1.1b decision.

**RA1.1b (2026-07-09) — Path 1 chosen; capability-URL deleted:**  
The half-day timebox confirmed that `mcp[cli]` 1.28 provides complete OAuth 2.1 authorization-server plumbing (`OAuthAuthorizationServerProvider` Protocol, `create_auth_routes()` returning 4 Starlette routes including `/.well-known/oauth-authorization-server`, `/authorize`, `/token`, `/revoke`). Building the provider was a contained 5-file task, not hand-rolling OAuth from scratch — so Path 1 executed.

What shipped (RA1.1b):
- `backend/alembic/versions/0b1c2d3e4f5a_oauth_tables.py` — `oauth_auth_codes` + `oauth_tokens` tables; purely additive; reversible `downgrade`.
- `backend/app/models/models.py` — `OAuthAuthCode` + `OAuthToken` ORM classes.
- `backend/app/services/oauth.py` — `AntonOAuthProvider` (9 async methods); `verify_access_token_sync` (sync DB check for ASGI middleware); `create_auth_code` (called by login page). Token security: 256-bit random (`token_hex(32)`); stored as SHA-256 hex; access tokens 1 h TTL; refresh tokens 30 days; rotated on use. Revocation by `pair_id` (random hex linking access + refresh pair).
- `backend/app/routers/oauth.py` — `GET/POST /oauth/login`; password form (stateless — all OAuth params in hidden inputs / query string); `secrets.compare_digest` on `ANTON_LOGIN_PASSWORD`; on success writes auth code and redirects to `redirect_uri?code=...&state=...`.
- `backend/app/main.py` — `require_auth_config()` now requires only `ANTON_TOKENS`; `create_auth_routes()` wired conditionally on `ANTON_HOST_URL` (the OAuth issuer URL); `ANTON_CONNECTOR_TOKEN` removed from all config paths.
- `backend/app/middleware/auth.py` — capability-URL block deleted; `PUBLIC_PATHS` expanded to cover all OAuth protocol paths; OAuth access token fallback: when named-bearer check fails and `ANTON_HOST_URL` is set, calls `verify_access_token_sync` (sync SQLite lookup, sub-ms, acceptable under INV-9).
- `backend/tests/test_oauth.py` — 18 new tests: login form, wrong password → 401, correct password → redirect with code, code replay rejected, expired code rejected, expired/unknown token rejected, public OAuth paths, `get_client` registry.
- `ANTON_CONNECTOR_TOKEN` removed from env examples + `test_auth.py` capability-URL tests removed.

**Why:** The connector UI requires OAuth (GitHub issues #112/#411 — no bearer-header support). Capability-URL leaked into every log line (path segment = credential → RA1.3 log redaction would have been mandatory AND the gap between shipping the path and hardening logs was a window of exposure). Deleting dark code over keeping it was the right call.  
**Trade-offs:** `ANTON_TOKENS` change still requires a restart (same as E7/RA1.1). The test suite sets `ANTON_HOST_URL` in `test_oauth.py` module-level setup, so OAuth routes are wired for those tests; `test_auth.py` does not set it (keeps middleware tests focused on named-bearer behavior). SQLite sync calls in the async middleware path are acceptable under INV-9 (single-process, single-user).  
**Verdict:** ✅ Keep. Named bearer tokens (desktop/loopback/spa) + OAuth (claude.ai connector) are now the complete auth surface for RA1.

---

## Superseded Decisions (kept as history)

| Decision | Was | Superseded by | When |
|---|---|---|---|
| Two run stores (`strava_activities` + data-bearing `shoe_runs`) with dedup-by-link union | The Phase-3 accommodation of a frozen import beside live logging | B4 — canonical `activities` (`c3d4e5f6a7b8`) | 2026-07-04 |
| `strava_backfill` MATCH/BACKFILL reconciliation (plan-then-execute, mileage policies) | The bridge between the two stores | Made permanent, then deleted with them (its *process* pattern lives on in E4) | 2026-07-04 |
| Direct backend integration of the external COROS MCP in `chat_service` | First attempt at watch sync | C6 — client-side agent prompt (OAuth constraint) | recorded in `docs/changelog.md` |
| Single free-text `notes` column on owned shoes | Original journal | B12 — `shoe_notes` timestamped/mileage-anchored rows | recorded in `docs/changelog.md` |
| Scraper monolith (`scraper_manager` as implementation) | Pre-refactor | D1/D7 — decomposed modules behind a shim | 2026 refactor |
| `scraper_manager.py` compat shim (`ScraperManager` alias) | Post-refactor transition scaffolding | D7 — deleted; consumers import `ScrapeOrchestrator`/`lock`/`registry` directly | 2026-07-07 (R1.5b) |
| APScheduler dependency (declared, unused) | Anticipatory install for scheduled scraping | E5 — dropped from `requirements.txt`; reinstate with an R4.1 design | 2026-07-07 (R1.6) |
| Per-size shoe tracking | Original watchlist shape | B2 — size-less tracking | recorded in code comment |
| No authentication anywhere (`0.0.0.0` default bind) | Trust = network posture, single trusted machine | E7 — shared bearer token on `/api`+`/mcp`, `127.0.0.1` default bind | 2026-07-07 (R2.1) |
| Single shared `ANTON_SECRET` for all clients (E7) | One baked-in secret; acceptable for trusted LAN; no per-client revocation | E9 — named per-client tokens + OAuth 2.1; `ANTON_SECRET` rotated | 2026-07-09 (RA1.1) |
| Capability-URL connector auth (`ANTON_CONNECTOR_TOKEN`) — RA1.1 Path 2 | URL as credential (`/mcp/<token>/...`); shipped as dark fallback | E9 RA1.1b Path 1 — OAuth 2.1 chosen; capability-URL code deleted from middleware, tests, env examples; never went public | 2026-07-09 (RA1.1b) |
| Dual schema authority (`create_all` + Alembic + `legacy_migrations/`) | `create_all` boot path kept for zero-step fresh setups | A6 — Alembic sole authority; baseline recreates the schema; legacy scripts deleted; DB moved to `~/anton-data/` | 2026-07-07 (R2.2) |
| Chat history + checkpoint state in browser localStorage | Simplest persistence during assistant build-out | C10 — server-side `chat_conversations` + `checkpoint_prompts`; start-fresh, no migration | 2026-07-08 (R2.6) |

---

*Maintenance note: add an entry when a decision is made that a future session might reasonably reverse; move reversed decisions to the Superseded table with the succeeding entry named. The ⚠️ scheduled-to-change to-do list is now **empty** — C8 (chat memory) was executed 2026-07-08 (R2.6 → C10), the last one; A6 was executed 2026-07-07 (R2.2 → Superseded) and E1 by R2.1 (→ E7). (D7 shim and E5 APScheduler were executed 2026-07-07, R1.5b/R1.6.)*
