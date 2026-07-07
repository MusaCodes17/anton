# Anton — Product Roadmap

**Generated:** 2026-07-04. **Inputs:** REDESIGN_PLAN Phase-5 backlog, standing wishlist items recorded in `docs/changelog.md`, the ⚠️ verdicts in `docs/design_decisions.md`, and `docs/architecture.md` §16.
**Framing:** Anton is evolving from a finished redesign into a long-term personal AI platform. This roadmap sequences that evolution.

**Naming note:** "Phase N" already means *redesign* phases in this repo's history (`p1:`…`p5:` commits). Roadmap phases are prefixed **R** (R1–R5) to avoid collision. Suggested commit prefix: `r2:` etc.

**Complexity scale:** **Low** = within one session · **Medium** = 1–3 sessions · **High** = multi-session, deserves its own §-numbered plan doc first.
**Standing rule inherited from the redesign:** backend + tests before UI; suite green + changelog entry per session; the confirmation-gate posture (design_decisions C9) applies to every agent below.

---

## R1 — Immediate Priorities

*Close the loose ends the redesign and today's migration left behind. Everything here is small, and everything after benefits.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R1.1 | **Commit & finish the documentation program** | ✅ **Done 2026-07-06** (documentation-completion session): the suite + `refactoring/` + `CLAUDE.md` + the rename committed as `docs: complete Phase 1 documentation program`; same session added CLAUDE.md §14 (INVARIANTS) and implemented `.claude/skills/` (13 files). Row moved to project_state §3. | Every future AI session boots on these files; uncommitted docs are one `git clean` from gone. | none | Low |
| R1.2 | **Prune the stale reference sections in `docs/changelog.md`** | ✅ **Done 2026-07-06** (docs-reconciliation session): tail replaced with a pointer into `docs/`; the Retailer Status table was relocated to `architecture.md` §10 first; header retitled. Changelog entries above were untouched. | The changelog is the most-read file in the repo; wrong reference material there actively misleads new sessions. | none | Low |
| R1.3 | **Wire the Replacement Deals card on `/shoes/:id`** | The detail page has held a "Coming soon" placeholder since June; its data dependency (`rotation.retirement_pipeline` / `active_deal_counts_by_type` + `/deals?deal=` deep links) shipped 2026-07-04. Render matching active deals (same `shoe_type`) on the shoe detail page. | Closes the oldest visible loose end; makes the cross-domain bridge useful exactly where retirement decisions happen. | none (data exists) | Low |
| R1.4 | **Guard the `ShoeRun` proxy traps** | Eager-load the `activity` relationship at every list seam (`get_shoe_runs`, resources, run history); add a warning comment on the model against `.filter()` on proxied attributes. | Today's migration left exactly one loaded gun for future code (N+1 + silently-broken filters). Cheapest possible insurance, best done while fresh. | none | Low |
| R1.5 | **Debt sweep #1** | One session, four moves from `dependency_graph.md` §11: (a) Task D — move `_attach_computed_fields` into the services layer, deleting the router→router import; (b) delete the `scraper_manager` shim (4 call sites); (c) extract a pure `pace` module (3 duplicate implementations); (d) single-source the chat model catalog. | Clears every ⚠ flag in the dependency graph except fat routers; each item is small but they compound into real drift risk if left. | none | Low–Medium (one session, four commits) |
| R1.6 | **Decide APScheduler** | Remove the unused dependency, or write the §-plan for scheduled scraping (R4.1) that justifies it. Removal is the default. | A dependency without an architecture invites drive-by wiring that would collide with the single-process scrape lock. | none | Low |

**Order within R1:** 1 → 2 → 4 → 3 → 5 → 6. (Docs safety first; the proxy guard before any session writes new run-path code; the card is a nice small win; sweep and decision close the phase.)

---

## R2 — Core Platform

*Turn "works on my machine, trusted LAN" into a platform that can safely grow interfaces. R2 is the gate in front of R3–R5.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R2.1 | **Security pass** | Shared bearer token enforced on `/api` and `/mcp` (Claude Desktop's `mcp-remote` and `chat_service`'s loopback client both send it); default bind to `127.0.0.1` with an explicit opt-out env for LAN use; basic rate limiting on `/api/chat/message`. | The acknowledged precondition for *everything* exposure-increasing (agents running unattended, mobile, remote MCP). Converts the trust model from network posture to application property. Currently anyone reaching port 8000 can mutate data and spend LLM credits. | none — do first in R2 | Medium |
| R2.2 | **Schema authority resolution** | Alembic becomes the sole schema source: `create_all` demoted to test fixtures; `legacy_migrations/` archived; live DB + `.bak*` files relocated out of the tree (e.g. `~/anton-data/`) with a dated-backup convention; `DATABASE_URL` already supports the move. | Ends the "model edit without migration silently diverges" trap and the five-backups-next-to-source ambiguity. Prerequisite hygiene for every future migration. | R1.1 (docs committed — paths change) | Medium |
| R2.3 | **Indexed read paths over the canonical table** | Swap `unified_activities` internals from whole-table Python to SQL date-range/shoe/pagination queries (the seam guarantees zero caller changes); extract `services/watchlist.py` from the fat router the same way. | Home's <200 ms budget vs. a growing decade of history; watchlist extraction is also what unlocks MCP watchlist parity (R3.4). The canonical table was built to make this possible — cash it in. | R1.4 (eager-loading conventions set) | Medium |
| R2.4 | **Shoe-type controlled vocabulary** | Promote `shoe_type` from free strings to a small backend-owned vocabulary (lookup table or enum) used by both domains and *served* to the frontend (deleting `lib/shoeTypes.js` as an independent copy). | The cross-domain bridge is the most load-bearing string set in the system; a typo currently fails silently. Three copies exist today. | none | Low–Medium |
| R2.5 | **Scrape observability** | Persist scrape runs/attempts (per retailer: started, finished, product count, error) written by the orchestrator; surface per-retailer health + trend in Settings → Sync & Scraping. | "Is Altitude quietly broken?" becomes a query instead of log archaeology. The substrate R4.1 (scheduling) and R4.5 (watchdog) require. Forces the documented decision on the single-process lock. | none | Medium |
| R2.6 | **Server-side conversation & memory persistence** | Move Son of Anton conversations (and checkpoint-prompt state) from localStorage into the backend (tables + endpoints), keeping the client stateless-per-request contract. | Device-bound memory contradicts the API-first multi-client principle; agents (R3) need shared context; quota-trimming currently discards history silently. Scheduled-to-change in design_decisions C8. | R2.1 (chat endpoints stop being anonymous) | Medium |

**Order within R2:** 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6. (Security first on principle; schema hygiene before anything that adds tables — 2.5 and 2.6 both add tables and should be born as clean migrations.)

---

## R3 — AI Capabilities

*The redesign built the surfaces; R3 populates them. Every agent obeys C9: prepare and propose, the runner disposes.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R3.1 | **Weekly Rotation Summary Agent** | An MCP prompt (sibling of `sync_coros_runs`) + on-demand trigger that composes the week: km vs last week, per-shoe usage, pipeline movement, checkpoints crossed, notable runs — rendered as a digest the runner reads Monday. Backlog item with its surfaces (Home, Training) already built. | The first *proactive* value from the AI layer, built almost entirely from existing tools (`get_training_summary`, `retirement_pipeline`, `get_shoe_runs`). Proves the agent pattern cheaply. | none hard; R2.6 makes digests persistent | Medium |
| R3.2 | **Deal Alert Agent** | Detection + digest for deal *events*: new qualified deal on a tracked shoe, price-drop on an active deal, replacement-deal appearing for a pipeline shoe. On-demand/"since last check" first (persisted high-water mark); push delivery arrives with R4.2. | The deals domain's whole purpose is timely opportunity — today it requires opening the app. Backlog item; Home top-deals module is its surface. | R2.5 helps (event source); delivery beyond in-app needs R3.5 | Medium |
| R3.3 | **Shoe review pipeline maturation** | Grow `draft_shoe_review` (MCP sampling) into a workflow: retirement → prompt to review → draft from the notes journal → runner edits → stored on the shoe (and exportable). | The notes journal exists to feed this; retirement is its natural trigger; it's the payoff of the mileage-anchored journaling discipline. | R1.3 pattern (detail-page work); storage column | Low–Medium |
| R3.4 | **MCP watchlist parity + resource expansion** | Expose the watchlist through MCP (tool + resource) once R2.3 extracts the service; consider a `training://summary` resource for chat pre-priming. | Son of Anton currently can't answer "what am I watching and what's the best price ever?" — the only major read surface missing from the AI layer. | R2.3 | Low |
| R3.5 | **Notification channel (Email MCP or equivalent)** | One outbound channel for agent output — the explored Email MCP, or the simplest reliable alternative (e.g. a digest endpoint the phone reads). Decide once, use for R3.1/R3.2/R4.5. | Agents that can only speak when spoken to aren't agents. Channel choice is a one-time decision every proactive feature reuses. | R2.1 (an authenticated system shouldn't email from an open one) | Medium |
| R3.6 | **Race-block training advisor** | A prompt-encoded advisor over existing data: weeks-to-race (planned_races), recent volume/paces (training summary), rotation state — producing block-level observations ("9 weeks out, volume trailing your Ottawa build"). Advisory text only; no plan-generation pretensions. | Highest-value reasoning use of data already collected; zero new schema. The runner's actual use case (sub-2:37 target). | R3.1 (shares digest machinery) | Medium |

**Order within R3:** 3.1 → 3.4 → 3.3 → 3.2 → 3.5 → 3.6. (Weekly summary proves the pattern; parity and reviews are cheap wins on existing rails; alerts + channel together; advisor last as the most judgment-heavy.)

---

## R4 — Automation

*Remove the human trigger where — and only where — the human isn't the point. Confirmation gates on writes remain non-negotiable.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R4.1 | **Scheduled scraping** | Nightly (or N-hourly) scrape runs via a real design: persisted job state, DB-level or documented single-process coordination replacing the bare in-memory lock, per-retailer staggering, failure recording into R2.5's tables. This is where APScheduler earns re-admission (R1.6). | Deal data is only as good as its freshness; manual triggering is the platform's biggest remaining chore. | R2.5 (observability), R1.6 decision; R2.1 before exposing any trigger surface | Medium–High |
| R4.2 | **Agent scheduling & event delivery** | Weekly summary auto-runs Monday morning; deal alerts fire on new-deal events from scheduled scrapes; both deliver via R3.5's channel. | Turns R3's on-demand agents into ambient value — Anton starts *telling* the runner things. | R3.1, R3.2, R3.5, R4.1 | Medium |
| R4.3 | **Semi-automated COROS cadence** | Within the Claude-Desktop-mediated constraint (design_decisions C6): a "runs pending sync" nudge (Home strip already shows last-sync) + one-tap launch of the `sync_coros_runs` flow. Full automation is *not* possible while COROS OAuth is desktop-managed — design to the constraint, don't fight it. | Sync friction is the main data-freshness gap on the training side. | R3.5 (nudge channel) | Low–Medium |
| R4.4 | **Coupon Hunting Agent** | Periodic promo-code discovery beyond the current homepage regex: agent-driven checks of retailer promo pages, validated codes landing in `promo_codes` (source=`scraped`; manual still wins). Explored-and-deferred wishlist item. | Stacking a promo on a qualified deal is real money; currently ad-hoc. | R4.1 (scheduler), scraper heuristics | Medium |
| R4.5 | **Scraper watchdog** | Trend rules over R2.5 data: "retailer X has returned 0 products for 3 runs" → alert via R3.5. | Silent scraper death is the current failure mode (visible only in logs); the deal feed degrades invisibly. | R2.5, R3.5, R4.1 | Low |

**Order within R4:** 4.1 → 4.5 → 4.2 → 4.3 → 4.4.

---

## R5 — Long-Term Vision

*Anton as a durable personal platform: reachable anywhere, ingesting everything relevant, reasoning across a decade of data. Everything here deserves its own plan doc before code.*

| # | Item | Description | Why it matters | Dependencies | Complexity |
|---|---|---|---|---|---|
| R5.1 | **Native mobile client** | The long-anticipated app: Home as launch screen (built to budget for this), log-run + sync-nudge + deal alerts as the core loop. Precede with a typed/generated API contract (OpenAPI client) — the moment a second consumer exists, hand-matched string contracts stop scaling (design_decisions A5's named trigger). | The platform's stated destination; every API-first discipline since Phase 1 was bought for this. | R2.1 (hard gate), R2.6, R3.5; contract-generation spike | High |
| R5.2 | **Remote access story** | Decide how Anton is reached off-LAN: private overlay (Tailscale-style) vs hosted. Revisit the deferred remote-MCP-for-ChatGPT transport here, not before. | Mobile off-WiFi and any third-party MCP client both need this answered; it's a security-architecture decision, not a feature. | R2.1, R2.2 | Medium–High |
| R5.3 | **Purchase-loop closure** | Optional provenance from deal → owned shoe: "I bought this" on a deal creates/links an owned shoe with purchase price pre-filled. Must respect B1 (wanting ≠ owning): an *optional recorded event*, never a forced workflow or FK entanglement. | Closes the platform's narrative loop (watch → buy → run → retire → replace) and feeds real cost/km from day one. | R2.4 (shared vocabulary) | Medium |
| R5.4 | **Richer ingestion** | Candidates, each its own decision: per-run FIT-file detail (COROS MCP already exposes FIT downloads) for splits/HR curves; periodic Strava re-exports folded in via the existing idempotent importer; weather-at-run enrichment. Gate each on a question it answers, not on data availability. | The canonical `activities` table is deliberately a superset schema — it can absorb richer data without restructuring. | R2.3; per-source spikes | High (aggregate) |
| R5.5 | **Longitudinal analytics** | The decade-scale questions: shoe-model performance correlations (pace/HR by shoe across years), wear-rate curves by type, injury-pattern context (the recurring left-leg history) annotated against volume spikes. Read-only analytics over `activities` — no new writes. | This is why eight years of history was imported and made canonical: Anton's endgame is *insight*, not logging. | R2.3, R5.4 helps | High |
| R5.6 | **Documentation as infrastructure, permanently** | The Phase-2 (implementation) workflow from `documentation_creation.md`: milestone plans executed by cheaper coding agents, with `project_state.md` / `roadmap.md` / `design_decisions.md` updated continuously as living artifacts. | The meta-bet of this whole program: sessions that start with accurate context outperform sessions that start with archaeology. | R1.1 | Ongoing |

**Order within R5:** 5.2 and the R5.1 contract spike can start once R2 lands; 5.3 anytime after R2.4; 5.4/5.5 follow data needs, not a schedule.

---

## Dependency Spine (the short version)

```
R1 (loose ends) ─▶ R2.1 Security ─▶ R2.2 Schema ─▶ R2.3 Indexed reads ─┬▶ R3 agents ─▶ R4 automation ─▶ R5.1 Mobile
                                                                        └▶ R5.2 Remote access
R2.5 Observability ─▶ R4.1 Scheduling ─▶ R4.2/4.5
R3.5 Channel ─▶ everything proactive
```

Two rules fall out of the spine: **nothing unattended before R2.1**, and **nothing scheduled before R2.5**. Everything else is negotiable in order.

---

*Maintenance note: this file is a living artifact (see R5.6). When an item ships, move its row into `project_state.md` §3 and record any decision it embodied in `design_decisions.md`. When priorities change, re-order here and say why in the changelog entry — the roadmap's history is part of the roadmap.*
