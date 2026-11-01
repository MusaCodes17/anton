# R14 — Lean MCP read payloads (plan)

**Status:** planned 2026-10-31, not started. In-flight plan doc: when it ships, move lasting findings into `design_decisions.md` + tool docstrings and delete this file.
**Commit prefix:** `r14:` · one commit per numbered task · ends with S13 wrap-up.
**Complexity:** Low–Medium (one session). MCP adapters + `_shared` projections + tests. No schema, no REST shape change, no frontend.
**Second purpose:** first real session under the R13 hooks. §3 lists the live checks R13 couldn't do. Record each outcome in the changelog.

---

## §0 Why

Every MCP read result goes straight into the client's context: Claude Desktop, claude.ai, and Son of Anton (in-process, C14). Several tools return the REST schema in full, unbounded:
- `get_shoe_runs` returns **every** run on the shoe as a full `ShoeRunResponse`, no limit. A 700 km shoe is ~70+ runs.
- `get_owned_shoes` returns full `OwnedShoeResponse` for **all** shoes when no filter is given (retired included), with every computed field.
- Resources `shoes://rotation` and `shoes://owned/{id}/runs` send the markdown **and** a full JSON copy of the same data.
- Likely others (`get_deals`, `get_training_trends`, `get_shoe_insights` weekly wear series). T0 decides with numbers.

Precedent for LLM-specific projections already exists: `_deal_to_dict` (a flat hand-written shape) and R12's lean `inbox_view`. REST/MCP parity (§4.2) is about *capability* parity; the REST schemas that serve the UI don't change.

## §1 Design rules (apply to every tool touched)

1. **Brief by default, `detail=True` for the old shape.** `detail=True` must return byte-for-byte what the tool returns today, locked by a regression test. Nothing that needs the full record loses it.
2. **Bounded lists:** `limit` (default 20, max 200) + `offset`, and the response carries `total` and `has_more`. Newest first, as now.
3. **Brief shapes are named projections in `_shared.py`** (`_owned_shoe_brief`, `_shoe_run_brief`, …), not ad-hoc dicts in tools, so the next tool reuses them. Docstring: "LLM projection; the REST schema is the full record."
4. **Units stay in names** (§5): `distance_km`, `current_mileage_km`, `avg_pace` (M:SS/km string, presentation), `pct_of_limit`.
5. **Docstrings are the contract** (§13): say the default is brief, what `detail` adds, and how to page.
6. Derived numbers are still computed server-side once (philosophy #1). A brief shape *drops* fields; it never re-derives them.

---

## §2 Tasks

Model hints are for /orchestrate. Opus reviews every diff against §1 + CLAUDE.md §14.

### T0 — Measure · Haiku
Add `backend/scripts/spikes/mcp_payload_sizes.py`: calls every read tool and resource in-process against a **copy** of the live DB (`sqlite3 -readonly ~/anton-data/shoe_deals.db ".backup /tmp/anton-r14.db"`, then `DATABASE_URL` pointed at the copy). It prints a table: tool, args used, chars, ≈tokens (chars/4). For per-shoe tools, use the highest-mileage active shoe. Paste the table into the changelog draft.
**Scope rule:** anything over ~1,500 tokens is in scope. The rest stay as-is (list them as measured and left alone).

### T1 — Brief projections · Sonnet
`mcp_server/_shared.py`:
- `_owned_shoe_brief(shoe)` → `id, name (brand model + nickname), shoe_type, status, current_mileage_km, mileage_limit_km, pct_of_limit, total_runs`. Uses the attributes `attach_computed_fields_bulk` already set. No new queries.
- `_shoe_run_brief(run)` → `run_id, date, distance_km, avg_pace, avg_hr, activity_tag, source`. Reads `run.activity` (eager-loaded by the caller, known trap).
- **Tests first** (`tests/test_mcp_projections.py`): exact key sets, nickname formatting, `pct_of_limit` null when no limit, and that a brief shape never contains fields absent from the full one. Write and run these *before* the projections exist. This is the planned trigger for the async-wake check (§3 H3).

### T2 — `get_owned_shoes` · Sonnet
Add `detail: bool = False`. Brief list by default; `status_filter` semantics unchanged (omit = all). Add `include_retired: bool = True` only if T0 shows retired shoes dominate the payload. Otherwise leave it out.
Tests: default is brief; `detail=True` equals the pre-change output (snapshot from a fixture rotation); filter still works.

### T3 — `get_shoe_runs` · Sonnet
Add `limit=20, offset=0, detail=False`. Push limit/offset into the query (no load-all-then-slice). Return `owned_shoe_id, runs, total_runs, has_more, lifetime_avg_pace, lifetime_avg_hr`. Lifetime stats are still computed over **all** runs.
Tests: boundaries named explicitly (§10): exactly `limit` runs → `has_more` false; `limit`+1 → true; `offset` past the end → empty list, `has_more` false; `limit` clamped to 200; lifetime stats identical to before regardless of page; `detail=True, limit=200` equals the old full output for a shoe under 200 runs.

### T4 — Resources: drop the duplicate JSON · Sonnet
`shoes://rotation` and `shoes://owned/{id}/runs` currently embed full JSON *and* markdown. Keep the §6 envelope ("resources return markdown *with* an embedded JSON block"), but make the JSON block use the **brief** projections. The runs resource caps at the newest 50, with a "N older runs: use get_shoe_runs(offset=…)" line. If that conflicts with any consumer (T6), stop and ask rather than change the envelope rule.

### T5 — Other offenders from T0 · Sonnet (one commit each)
For each tool over the T0 threshold, apply §1. Likely shapes:
- `get_shoe_insights` / `get_training_trends`: weekly series → keep the last 12 weeks + a monthly roll-up by default; `full_series=True` for everything.
- `get_deals`: `limit` + brief deal (`id, shoe, retailer, price, savings_percent, size_fit, url`).
Same test pattern as T3. Stop at 3 tools. More goes to a follow-up row.

### T6 — Consumer audit · Haiku
Grep prompts (`@mcp.prompt` bodies), `chat_service`, `chat_proposals`, and `docs/CLAUDE_DESKTOP_SETUP.md` for fields that are now detail-only (`purchase_price`, `starting_mileage`, `review_draft`, per-run cadence/elevation…). For each hit, either pass `detail=True` at that call site or update the prompt. Son of Anton check: "how many km on my Evo SL" and "show my last 5 runs in the AP4" answered in the app chat without a `detail` call.

### T7 — Re-measure + S13 wrap-up · Haiku
Re-run T0's script and put a before/after table in the changelog. Record the §3 hook outcomes. Add a `design_decisions.md` entry ("MCP read tools default to brief LLM projections; `detail=True` returns the REST record; lists are paged"). Update `project_state.md`, delete this file and the spike script, or keep the script under `scripts/` if it's useful for future tools.

---

## §3 Hook live checks (R13 left these unverified)

Do them as the work happens; most fire on their own. Record ✅/❌ + one line each in the R14 changelog entry. A ❌ is a bug in R13, so fix it in a separate `r13:` commit, not mixed into r14 tasks.

| # | Check | How it gets triggered | Expected |
|---|---|---|---|
| H1 | PreToolUse **ask** on live DB | T0's `sqlite3 ... ~/anton-data/shoe_deals.db` copy command | The first form, *without* `-readonly`, prompts. The `-readonly` form passes. (Try both deliberately.) |
| H2 | PreToolUse **deny** | Ask Claude to "add a line to backend/.env" (then cancel) | Denied with the guard's reason; file untouched |
| H3 | `asyncRewake` wake on failure | T1 tests written before the projections exist | Edit returns immediately; a moment later Claude is woken with the failing test tail |
| H4 | PostToolUse syntax check | Happens if any edit leaves a `.py` file unparsable; or deliberately: one edit with an unclosed bracket, then fix | stderr reaches Claude right after the edit |
| H5 | SubagentStop **block** | A subagent finishing T1 with tests still red | It's kept working (or returns the failure). The orchestrator doesn't receive a green-looking result |
| H6 | Stop **block** + loop guard | End the main turn once with a red test (deliberately, after T3) | Blocked with the tail. On a third failure at the same tree, it lets go with the "still failing" message |
| H7 | Silent on success | Every green edit/stop in the session | No hook output in the transcript at all |
| H8 | Worktree resolution | Run the session in a `.claude/worktrees/` checkout | Hooks check the worktree's files, use the main checkout's venv |
| H9 | PostToolUse colour check (optional; no frontend in R14) | Throwaway edit adding `#ff0000` to a component, then revert | Flagged |

## §4 Invariants / review checklist
- No write tool touched; INV-1…INV-8 paths untouched.
- `detail=True` regression tests exist for every changed tool.
- No load-all-then-slice in paged queries. `ShoeRun.activity` eager-loaded in every run loop (N+1 trap).
- REST schemas and responses unchanged (`git diff` touches no router or `models/schemas/`).
