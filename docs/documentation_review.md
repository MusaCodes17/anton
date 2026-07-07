# Anton — Documentation Program: Final Review

**Deliverable of the Final Review Prompt** (`documentation_creation.md`). **Generated:** 2026-07-06, immediately after prompt 10 (`docs/ai_context.md`) completed.
**Scope:** every document produced by the program — `docs/{architecture, project_state, roadmap, dependency_graph, design_decisions, domain_model, skills_library, ai_context}.md`, `CLAUDE.md`, `refactoring/{refactor, tech_debt, dead_code}.md`, plus `docs/changelog.md` (the renamed session log) — reviewed *together* against the tree at the **MSRP-drives-deals** state (2026-07-06; `models.py` 18,858 bytes; suite 64 passing; migration `d4e5f6a7b8c9`).
**What this file is:** recommendations for improving the documentation itself. No code findings (that was Prompt 6), no code changes.
**Verified first-hand this session:** every file above was read in full; root `claude.md` is confirmed **gone** (renamed to `docs/changelog.md`); `docs/changelog.md`'s stale pre-Phase-5 reference tail is confirmed **still present** (read this session — old `shoe_runs` columns, target_price deal schema, the retired `/scrape/test/*` endpoints); `docs/ai_context.md` confirmed on disk at 21.3 KB.

---

## 1. Overall verdict

The suite is unusually coherent for thirteen documents produced across multiple sessions: responsibilities are cleanly divided (architecture = system, domain_model = meaning, design_decisions = history, dependency_graph = imports, tech_debt = ranked index, refactor = line-level findings, dead_code = deletion inventory, project_state = perishable snapshot, roadmap = sequencing, CLAUDE.md = conventions, ai_context = orientation), cross-references are dense and mostly accurate, and every file carries a maintenance note saying when it goes stale. The two structural habits worth calling out as *strengths to preserve*: **cite-don't-restate** (skills_library's authoring rule, honored almost everywhere) and **strike-with-pointer, never delete** (refactor/tech_debt/design_decisions all encode it).

The problems found fall into three families: **(a)** a one-day freshness ripple from the 2026-07-06 MSRP change that landed *after* most of the suite was written — mechanical to fix, but currently the suite's only genuine contradictions; **(b)** naming/count drift left by the `claude.md → docs/changelog.md` rename and the 61→64 test-count move; **(c)** a small set of genuinely missing artifacts (the INVARIANTS section, a config reference, the skills implementation). Nothing found undermines the suite's architecture; everything below is repair and completion.

---

## 2. Contradictions and inconsistencies (ranked; each with the exact fix)

> **Struck 2026-07-06** — every item in this section (§2.1–§2.6) was applied by the same-day docs-reconciliation session; see the changelog entry "Documentation program complete — final review + docs reconciliation." Preserved below for the record.

### 2.1 The MSRP ripple — the only true contradictions in the suite ⚠️ fix first

`design_decisions.md` was correctly updated same-day (B9 → Superseded, **B9-v2** added, B8 amended). The rest of the suite still describes the old rule:

| File | Stale content | Fix |
|---|---|---|
| `domain_model.md` §4.1 | "A Deal exists iff… genuinely discounting AND ≤ current target price" + both corollaries | Rewrite §4.1 to the B9-v2 rule (`price < msrp`, savings vs MSRP, no-MSRP → no deals); keep the old rule as a one-line historical note pointing at B9 |
| `domain_model.md` §2.1 (Tracked Shoe) + §7.1 glossary ("deal", "target price") | target_price described as the deal driver; msrp "optional" | msrp is the required deal driver; target_price is an optional personal threshold |
| `architecture.md` §6 (Watchlist aggregate invariant) and §12 (deal-pipeline diagram: "qualify: on_sale AND price ≤ current target") | Old qualification in both places | One-line updates to `price < msrp`; §12's diagram line likewise |
| `architecture.md` §5 `shoes` table row | "`target_price`, `msrp` (kept separate so 'at target' ≠ 'below MSRP')" | Reverse the emphasis: msrp drives deals, target optional/nullable |
| `CLAUDE.md` §9 + `design_decisions.md` B13 | "the two blessed exceptions… a deal's **qualified-target** snapshot" | "a deal's qualifying-savings snapshot (MSRP-based since B9-v2)" |
| `refactoring/refactor.md` **L2** | "savings measured against target price… documentation-first fix" | **Strike with a pointer** to the 2026-07-06 changelog entry — resolved differently (savings now measured against MSRP); the finding's warning about the Deal Alert agent misreporting is moot |
| `refactoring/tech_debt.md` §9.5 | Mirrors L2 | Strike with the same pointer |
| `refactoring/refactor.md` + `tech_debt.md` freshness headers | "models.py at 18,151 bytes… nothing newer than 2026-07-04" | Per their own maintenance notes, re-stamp after re-verifying C1/H3/H4 (the MSRP change touched schemas/orchestrator/deal_store, not the rotation paths — expected outcome: findings stand unchanged) |
| `tech_debt.md` P1-4 / `refactor.md` H1 | "Deal domain: **zero** coverage" | Amend: `test_deals.py` (3 tests) now pins MSRP savings/refresh/no-MSRP; retirement/requalification, the orphan guard (H2 case), promo protection, and all HTTP-layer coverage remain open |

### 2.2 `docs/changelog.md` — verified stale tail + mistitled header

Confirmed this session: the bottom of the file still carries pre-Phase-5 reference sections that are **actively wrong** (a `shoe_runs` with data columns, deals keyed to target_price, the deleted `/scrape/test/*` endpoints listed as live, `expires_at` presented as meaningful). Worse, the file's own header still reads "**Running Shoe Deal Finder - Project State 📋**" with Status/Focus lines — it is neither project state (that's `docs/project_state.md`) nor current. Fix = roadmap **R1.2** exactly as written, plus: retitle the header to "Anton — Session Changelog", drop the Status/Focus lines (or point them at project_state.md), and replace the entire tail with one line: *"Reference material moved to `docs/` — see architecture.md."* This resolves tech_debt §9.7 from *Verify* to *Confirmed-and-fixed*.

### 2.3 `claude.md` naming drift (the rename's residue)

Root `claude.md` no longer exists, but the suite still cites it as if it did: `architecture.md` §3 folder tree ("claude.md # Living project log"), §14.8 and §16.8; `design_decisions.md` header, E3, C6, and the Superseded table ("recorded in claude.md" ×2); `domain_model.md` (none — clean); `dead_code.md` (clean — says changelog); `skills_library.md` S05 (already says changelog — clean). Fix: global touch-up replacing "claude.md" with "`docs/changelog.md` (the session log) / `CLAUDE.md` (the guide)" as appropriate. Low effort, high confusion-prevention — a new session grepping for `claude.md` today finds a ghost.

### 2.4 Count drift (tests, migrations, models)

- **Tests:** "61 passing" is hard-coded in `architecture.md` §2, `CLAUDE.md` §10, `project_state.md` §2, `dead_code.md` header/footer. Actual: **64**. Recommendation is a *process* fix, not just a number fix: the live count should be authoritative in exactly two places (the newest changelog entry and `project_state.md` §2); every other doc should say "suite green — count in the changelog" or carry an explicit as-of date (CLAUDE.md's "61 as of 2026-07-04" is the right *form*, just stale).
- **Migrations:** `architecture.md` §2 says "baseline + 4 migrations", `dependency_graph.md` §1 says "5 revisions"; actual is now baseline + 5 (`mileage_limit`, strava tables, `planned_races`, `canonical_activities`, `msrp_drives_deals`). Give the authoritative list one home — `architecture.md` §5's schema-management paragraph — and have dependency_graph cite it instead of counting independently.
- **Backups:** "five `.bak*` siblings" appears in architecture §3/§5 and tech_debt §1.8; there are now six (`.bak-msrp-drives-deals` added 2026-07-06). Same fix: stop counting in prose ("dated `.bak*` restore points, see E2") so the number can't drift.

### 2.5 `project_state.md` — expired snapshot

Dated 2026-07-04 and now wrong on: documentation-program status (§1/§2/§4 say prompts 3–8 + 10 remain; actually only this review remained, and it is now done), test count (61 → 64), the MSRP change (absent from §3/§9 — it belongs in Recent Architectural Decisions as the B9-v2 entry), and the "Current Focus" reading note (§1). This is *expected* decay per its own maintenance note, not a defect — but it should be the first file refreshed in the reconciliation session, because ai_context.md §12 sends every new session to it.

### 2.6 Small internal inconsistencies

- `dependency_graph.md` header revision note says "Parts of `architecture.md` §5–§6 describe the pre-migration schema and should be refreshed" — but architecture.md *was* refreshed the same day (its own header says so). Delete the stale sentence.
- `skills_library.md` header notes the changelog's Project Commands table lists five commands while only `migrate.md` exists on disk — still true; the R1.2 changelog prune should delete or correct that table too.
- `ai_context.md` §11 staleness register: written to be self-expiring — when the reconciliation session (§5 below) lands, prune the register in the same commit.

---

## 3. Missing documentation

1. **The INVARIANTS section** — flagged twice already (architecture §16.9, tech_debt §9.2) and endorsed here as the single highest-leverage missing artifact. domain_model §4 is the constitution but reads as prose; refactor.md C1 is exactly what happens when an invariant lives in prose only. Recommendation: a short checkable list (one line per invariant + its owning code path + its test, ~20 lines) placed in **CLAUDE.md** (the one file every session reads), with domain_model §4 as the narrative behind it and **ai_context §8 rewritten to cite it** rather than carrying its own copy — otherwise the suite will soon have three divergent "never break these" lists (see §4.3).
2. **A configuration/environment reference.** dependency_graph §8.10 observes that feature availability is an emergent property of `.env` contents (three LLM keys, COROS credentials-as-feature-flag, `MCP_SERVER_URL` self-reference, `DATABASE_URL`, `ALLOWED_ORIGINS`, bind address) — but no document lists the variables, their defaults, and what their absence does. One table in architecture.md (new §, or appended to §13) closes it. The `MCP_SERVER_URL` trap alone justifies it.
3. **The skills library is designed, not built.** `.claude/skills/` does not exist; skills_library.md is a spec. Implementation order is already given (S13 + S01 first). Until built, ai_context §12's pointer is the mitigation.
4. **`QUICKSTART.md` / `TROUBLESHOOTING.md` were never audited** by the program. Both predate the redesign and Phase 5; S12 (debugging) cites TROUBLESHOOTING.md as required context, so if it's stale it will actively mislead. One verification pass, or a header note dating them.
5. **A backup/restore runbook.** E2 records the *practices* (pre-migration `.bak`, `export.py` seed regeneration) but no doc says "how to actually restore" (file swap + Alembic replay caveat noted in dead_code §2.1). Three sentences in architecture §5 would do; matters more once R2.2 relocates the files.
6. *(Minor)* An MCP tool index. The docstrings are the contract (correct), but no human-readable inventory of the ~20 tools exists outside the code. Defensible to skip; if R3 grows the surface, generate one.

## 4. Overlap (mostly healthy — rules to keep it that way)

1. **Debt lives in four documents** (architecture §15, dependency_graph §§7–11, tech_debt, refactor) — acceptable because each has a distinct axis and tech_debt is the declared index, but the discipline must stay: *rank only in tech_debt, describe only once, cite everywhere else*. The MSRP ripple shows what happens when one axis updates and three don't.
2. **`architecture.md` §16 vs `roadmap.md`** — §16's nine directions are now all roadmap rows (16.1→R2.1, 16.2→R2.2, 16.3→R2.3, 16.5→R2.4, 16.6→R2.5, 16.7→R2.6, 16.4→R1.4+, 16.8→R1.5, 16.9→§3.1 above). Annotate each §16 item with its R-number so the two lists cannot diverge; roadmap stays the sequencing authority.
3. **Three "don't break these" lists forming:** CLAUDE.md §6 traps, ai_context §8, and the proposed INVARIANTS section. Resolution per §3.1: INVARIANTS = the canonical invariant list; CLAUDE.md §6 stays the *mechanical traps* list (proxies, pins, timezone — how-to-not-trip, not what-must-hold); ai_context §8 becomes citations into both.
4. `project_state.md` §7's short debt list duplicates tech_debt's top ranks — fine for a perishable snapshot, but it should open with "ranked authority: `refactoring/tech_debt.md`" (it currently cites architecture/dep_graph, written before tech_debt existed).

## 5. Gaps in architecture (as documented)

Nothing structural is missing from the system description. Three documentation-level gaps: the **env-as-wiring** table (§3.2 above); an explicit statement somewhere normative that **"exactly one uvicorn worker" is a hard operational invariant** (architecture §15.2 calls it invisible — the fix is to make it visible: one line in CLAUDE.md §12 or the INVARIANTS list, plus a comment in `run.py` when code changes resume); and a **scraper-health runbook** ("retailer X returns nothing — now what") — S12 sketches it, R2.5 will obsolete it, but a five-line interim in TROUBLESHOOTING.md during its §3.4 audit is cheap.

## 6. Missing skills

The 13-skill design is complete for today's workflows. Two additions recommended, both gated:

- **S14 — `data-correction.md`** (after refactor.md C1's fix lands): the sanctioned way to adjust a mileage ledger, re-attribute a run, or repair a bad sync — the C1 investigation proved this workflow exists in practice (the UI's Adjust-mileage dialog) with no documented protocol. Write it *when* `rotation.adjust_mileage()` exists, not before.
- **A security-pass plan doc, not a skill** — R2.1 is Medium complexity but touches every client (SPA, `mcp-remote`, the loopback chat connection — the exact consumer dependency_graph §8.1 warns breaks silently). It meets roadmap's own bar for "deserves its own §-numbered plan doc first." Recommend writing `SECURITY_PASS_PLAN.md` (or a roadmap appendix) before the R2.1 session starts.

Confirmed-correct omission: no `deployment.md` (A1 — there is nothing to deploy; revisit at R5.2, as skills_library already says).

## 7. Missing design decisions

design_decisions.md is thorough; four candidates surfaced by reading the suite together:

1. **The manual mileage-adjustment capability** — the C1 discovery showed the UI *deliberately* ships an Adjust-mileage dialog, i.e. a real product decision (the runner may override the ledger) that was never recorded, which is precisely how it ended up contradicting domain_model §4.5. When C1's sanctioned fix lands, add a **B-series entry** (chosen: explicit `rotation.adjust_mileage()` as a third blessed ledger writer, recorded adjustments; why; trade-offs) and amend domain_model §4.5 in the same session.
2. **MCP tools call services/ORM directly, never REST** — a real architectural choice (parity via shared functions, not HTTP self-calls) currently only implied by A3/C1 and dependency_graph §3. One paragraph, C-series.
3. **The 35-minute frontend axios timeout for synchronous scrapes** — a deliberate accommodation of D3's politeness budget, recorded only in architecture §10 prose. One line appended to D3 or D4 suffices; skip a full entry.
4. **Checkpoint-prompt state in localStorage** — currently a parenthetical under C8/domain_model §4.10. It shares C8's fate (R2.6); fold it into C8's entry explicitly so the R2.6 session migrates both.

Also: when R1 items execute, remember the standing rule — **D7, A6, C8, E1, E5 flip to Superseded entries**, and tech_debt/refactor strike their rows with changelog pointers. The suite's credibility rests on that loop actually closing.

---

## 8. Recommended actions, in order

> **Progress 2026-07-06:** step 1 ✅ executed (the reconciliation session, including addendum items A1/A2/A3/A5 — A1's retailer-table relocation was sequenced before the changelog prune as required). Steps 2–6 remain open; **step 2 (commit the batch) is now the single most urgent action.** A4 stays gated on step 4.

1. **One "docs reconciliation" session (≤ half a session, no code):** apply every §2.1 MSRP-ripple fix; §2.2 changelog retitle + tail amputation (R1.2); §2.3 claude.md reference sweep; §2.4 count-drift fixes + the "counts live in two places" rule; §2.5 project_state refresh (which also records prompt 10 + this review as done); §2.6 small fixes; prune ai_context §11's staleness register. End with a changelog entry.
2. **Commit the entire suite as the R1.1 batch** — docs/, refactoring/, CLAUDE.md, ai_context.md, this file. Uncommitted, all of this is one `git clean` from gone.
3. **Write the INVARIANTS section** in CLAUDE.md (§3.1 above) and repoint ai_context §8 at it.
4. **Implement the skills library** (S13 + S01 first, per skills_library's own ordering), adding the one-line index to CLAUDE.md §3.
5. **Adopt the three anti-drift process rules** this review derives: live counts in exactly two files; the authoritative migration list in architecture §5 only; every ⚠️-execution session flips design_decisions + strikes tech_debt/refactor in the same commit.
6. **Queue the gated items:** env-var reference table and QUICKSTART/TROUBLESHOOTING audit (any quiet session); S14 + the B-series mileage-adjust entry (with C1's fix); the security-pass plan doc (before R2.1).

## 9. What was *not* found

For calibration: no contradictions between domain_model's business rules and the code they cite (post-MSRP-fix); no orphaned cross-references besides the `claude.md` ghosts; no case where two documents rank the same debt differently; no invariant asserted in one doc and denied in another. The B9→B9-v2 handling in design_decisions is the Superseded mechanism working exactly as designed — the failure was only that the *other* documents' update triggers didn't fire, which recommendation 5 addresses.

---

*Maintenance note: this file is a point-in-time review and does not need ongoing maintenance — strike its recommendations with changelog pointers as they execute (the reconciliation session should strike most of §2 at once). If a future full-suite review is run, supersede this file rather than editing it: the deltas between reviews are themselves information about whether the documentation system is holding.*

---

# Addendum — same-day probe completion (2026-07-06, later session)

*Append-only. Nothing above was altered. A second session executed the Final Review handover checklist against the same tree state (re-verified first-hand: `models.py` 18,858 bytes · MSRP entry atop the changelog · all 14 expected suite files present) and found the review above complete against `documentation_creation.md`'s seven required categories. Several checklist probes were not visibly run in the review above; they were executed this session by content-grep across the full suite. Findings below use A-numbers to avoid colliding with the sections above.*

## A1 — The Retailer Status table lives only in the changelog tail slated for amputation ⚠️
**What:** The suite's only which-retailers-work/blocked/untested inventory is the "🌐 Retailer Status" table at `docs/changelog.md` ~line 277 — *inside* the stale pre-Phase-5 reference tail that §2.2 above and roadmap R1.2 both recommend replacing with a single pointer line. Meanwhile `skills_library.md` S05 lists that exact table as **required context**, and S05's checklist ends with "status table updated." Executing R1.2 as written deletes S05's dependency. `architecture.md` §13 says only "Two retailers known-blocked" without naming them.
**Fix:** Before (or in the same commit as) the R1.2 prune, relocate the Retailer Status table to a durable home — `architecture.md` §10 (scraper architecture) or §13 (externals table) — refresh it, and repoint S05's required-context line. Amend recommendation §8.1 above to sequence this inside the reconciliation session.
**Priority:** High (it is the one place where executing this review's own backlog destroys documentation).

## A2 — The `shoe_type` vocabulary is named load-bearing everywhere and enumerated nowhere
**What:** domain_model §4.3 calls it "the single most load-bearing set of strings in the system"; tech_debt P1-5/refactor M2 count **four** unvalidated code copies; yet no document lists the actual values — the docs give only two examples (`daily_trainer`, `long_distance_racer`). A session touching the bridge must read `lib/shoeTypes.js` or the chat `SYSTEM_PROMPT` to learn the vocabulary. domain_model's own maintenance note anticipates recording it ("when the `shoe_type` vocabulary is formalized").
**Fix:** Enumerate the current value set once — a small table in domain_model §7.1 (or §4.3) marked "as-of" and flagged for replacement by R2.4's controlled vocabulary. One paragraph; do not wait for R2.4.
**Priority:** Medium.

## A3 — Two dependency_graph §8 hidden dependencies missing from CLAUDE.md §6 traps
**Verified covered:** §8.1 (MCP_SERVER_URL), §8.2 (ShoeRun proxies), §8.8 (dual schema authority — via CLAUDE §9's migration rule), §8.10 (env-as-wiring — via §3.2 above). **Not covered:** **§8.9** — `strava_stats` imports the private-by-convention `activities._effective_moving_s`, so a "safe" rename inside `activities.py` breaks stats with no import-level signal; and **§8.4** — the hand-matched router-prefix ↔ `api.js` string contract (plus duplicated SSE event literals), which CLAUDE §6's "Frontend data flow" pattern describes without warning about.
**Fix:** One trap line each in CLAUDE.md §6.
**Priority:** Low–Medium (both are exactly the "do not rediscover" class §6 exists for).

## A4 — `sync_coros_runs` full protocol exists only in source
**What:** The most complex workflow in the system is *summarized* well (architecture §9's one-paragraph protocol; cited as "the reference protocol" by CLAUDE §6, ai_context §12, S07) but its parameter-level contract — external COROS tool names/args, the date+distance dedup tolerance, the timezone rule, the confirmation gate wording — lives only in the `mcp_server.py` prompt body. dependency_graph §8.6 already flags that this encodes a third party's tool schema with no signal in-repo on breakage.
**Fix:** Defensible to leave (the prompt *is* the artifact and is version-controlled), but when S07 is implemented, its skill file should carry the step list + the external-contract table so breakage diagnosis doesn't require reading the prompt source. No standalone doc needed now.
**Priority:** Low, gated on skills implementation (§8.4 above).

## A5 — Terminology sweep (the checklist's dedicated probe): suite is clean, one stray
- **"Tracked Shoe"** canonical (18 uses, 5 docs); one stray **"watched shoe"** in `roadmap.md` — fix to "tracked shoe" in the reconciliation session.
- **"Retirement pipeline"** canonical (8 uses); "attention state/list" appears only inside its own definition gloss (domain_model §7.1: "Attention state for shoes ≥ 75%… Not a status") — correct, not drift. "Retirement band": zero uses.
- **"Son of Anton"** (product) / **`chat_service`** (module) / **"the assistant"** (generic role) are used in a consistent three-layer register across all docs — no fix.
- **p1–p5 vs R1–R5**: explicitly disambiguated by roadmap's *Naming note*; ai_context uses "R-phase" correctly — no fix.
- **Activity / run / shoe run / attribution**: consistent with domain_model §7.1 at spot-check depth across CLAUDE.md, architecture, dependency_graph.

## A6 — Probes run and passed (for calibration, extending §9 above)
S04's migration discipline is reproducible without reading the reference migration (plan-first → named backup → reversible → reconciliation-defined-before → round-trip → suite → changelog numbers — complete). Roadmap's dependency spine honors design_decisions' preconditions (R2.1 stated as the hard gate in roadmap R5.1 *and* ai_context §4). ai_context's "never change casually" list covers the load-bearing ✅ Keeps **including same-day B9-v2** — ai_context was correctly updated with the MSRP change, a second file (with design_decisions) that beat the ripple. skills_library's 13 skills cover CLAUDE.md §§3–4's placement workflows and the R1–R5 feature types, subject to §6 above (S14 + the security plan doc).

**Net effect on the backlog (§8):** insert A1 into step 1 (relocate the retailer table *before* the changelog tail prune) and add A2/A3/A5's stray-term fix to the same reconciliation session; A4 folds into step 4.
