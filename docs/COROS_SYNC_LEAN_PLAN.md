# R12 — Lean COROS sync from Claude (plan)

**Status:** planned 2026-10-31, not started. In-flight plan doc (CLAUDE.md §3): when it ships, move lasting findings into `design_decisions.md` + docstrings and delete this file.
**Commit prefix:** `r12:` · one commit per numbered task · ends with S13 wrap-up.
**Complexity:** Low–Medium (one session; T7 optional second).

---

## §0 Why — what's actually left to move

R5.7 already moved the heavy work server-side: the poller pulls COROS, dedups (INV-5), prefetches detail, and stores a suggestion (`coros_suggestion.suggest_shoe`) on every `pending_coros_runs` row. Claude no longer touches the COROS connector. So the remaining cost is **the conversation round trip itself**, as the `sync_coros_runs` prompt drives it today:

| Step | Today | Token cost driver |
|---|---|---|
| Prompt | ~1.5k-token prompt, incl. pace/distance bands Claude is told to re-reason with | Restates a rule the server already applied ("two renderings of one rule" — drift risk too) |
| Fetch | `fetch_unsynced_coros_runs` returns 14 fields/run | Most fields exist only so Claude can echo them back |
| Rotation | Step 2 calls `get_owned_shoes` (full payload per shoe) | Needed only to turn `suggested_shoe_id` into a name + km |
| Confirm | **N calls** to `confirm_coros_run`, each echoing ~15 fields, each returning a full `_owned_shoe_payload` | Scales linearly with backlog; the Vancouver-style backlog is the worst case |
| Summary | Claude sums km per shoe and spots thresholds | Arithmetic in the LLM (violates philosophy #1 in spirit) |
| Dismiss | Not possible from Claude ("dismiss in the app") | Extra trip to the app |

Note: the inbox path already confirms **by `pending_id`** using the row's own data (`coros_inbox.confirm`), and `coros.confirm_run` already back-fills location from the pending row. Nothing needs to be invented; it needs exposing to MCP in batch form.

**Target session shape:** `fetch` (lean table + rotation block) → runner replies → **one** `confirm_pending_coros_runs` call with ids → server-computed summary. INV-8 unchanged: still nothing logs without the runner's reply.

---

## §1 Tasks

Model hints are for /orchestrate (Haiku = mechanical, Sonnet = normal, Opus reviews every diff against this doc + CLAUDE.md §14).

### T0 — Roadmap row (docs) · Haiku
Add **R12 — Lean COROS sync from Claude** to `docs/roadmap.md` pointing at this file; bump the "Last updated" line.

### T1 — Inbox view service · Sonnet
`services/coros_inbox.py`: add `inbox_view(db) -> InboxView` (dataclass, read-only, no commit):
- `runs`: per pending row → `pending_id, date, distance_km, avg_pace, avg_hr, training_focus, suggested_shoe_id, suggested_shoe (brand+model string), suggestion_reason`.
- **Stale suggestion guard:** if the stored `suggested_shoe_id` is no longer `active` (retired/for_sale since queueing), recompute with `suggest_shoe` *for the view only* — never write it back (INV-7 style: derived at read time). Flag `suggestion_refreshed: true`.
- `rotation`: active shoes only → `id, name, shoe_type, current_mileage_km` (so Claude can resolve "put #43 in the Teal Evo" without `get_owned_shoes`).
- Reuse `pending_to_dict`; don't fork the field mapping.

Tests (`tests/test_coros_inbox.py`): rotation lists active only; retired suggested shoe → refreshed suggestion, row unchanged in DB; empty inbox → empty lists; dismissed/confirmed rows excluded.

### T2 — Batch resolve service · Sonnet
`services/coros_inbox.py`: `resolve_batch(db, items: list[BatchItem]) -> BatchResult`.
- `BatchItem`: `pending_id`, `action: "confirm" | "dismiss"`, `owned_shoe_id` (**required for confirm** — no "default to suggestion" shortcut; the caller passes the id the runner agreed to, keeping INV-8 explicit), optional `activity_tag`, `notes`.
- Loops over the **existing** `confirm` / `dismiss` — no new write path (INV-2). Each item commits on its own (as today), so one bad item can't roll back the others.
- Skip-and-continue (CLAUDE.md §7): `LookupError`/`ValueError` per item land in `errors[{pending_id, error}]`; `already_logged` counted, not an error.
- `BatchResult` computed server-side: `logged`, `dismissed`, `already_logged`, `errors`, `per_shoe[{shoe_id, name, km_added, new_mileage_km}]`, `thresholds[{shoe_id, name, threshold_km, message}]`, `checkpoints[...]`.
- Reject duplicate `pending_id` in one batch (ValueError before any write).

Tests: mixed confirm/dismiss/unknown-shoe batch → partial success, correct per-shoe sums; **ledger round-trip** (INV-1: Σ km_added == mileage delta); re-running the same batch → all `already_logged`, mileage unchanged (INV-5); threshold crossing reported once per shoe; duplicate id rejected with zero writes.

### T3 — REST parity · Haiku
`routers/coros_connect.py`:
- `GET /api/coros/pending/view` → `inbox_view`.
- `POST /api/coros/pending/resolve` body `{items: [...]}` → `resolve_batch`; whole-batch `ValueError` (duplicates) → 400; per-item failures stay in the 200 body.
Update the module docstring's endpoint list. Tests in the router test module (auth required — check `tests/test_public_surface.py` still passes untouched).

### T4 — MCP tools · Sonnet
`mcp_server/coros.py` (thin adapters over T1/T2):
- `fetch_unsynced_coros_runs(days_back=30, detail=False)`: default returns the **lean** `inbox_view` shape + `rotation` + existing status/warning keys; `detail=True` keeps today's full per-run fields for any caller that wants them. Keep `days_back` ignored-for-compat.
- New `confirm_pending_coros_runs(items: list[dict])` → `{"success": bool, ...BatchResult}`. Docstring = LLM contract: only after the runner replied; pass `owned_shoe_id` explicitly; activity_tag only if the runner said it (C9); dismiss is for runs that shouldn't count toward any shoe.
- `confirm_coros_run` stays (runs not in the inbox, older clients); docstring points to the batch tool as preferred.
- Re-export from `mcp_server/__init__.py`. Tests patch `app.mcp_server._core.get_session` (known trap).

Tests (`tests/test_coros_mcp_tools.py`): update `test_fetch_returns_pending_queue_with_suggestions_and_detail` → `detail=True`; new lean-shape test; fetch → batch confirm end-to-end clears the app inbox; batch tool never raises (returns `success: False` on duplicate ids).

### T5 — Prompt rewrite + single-source the heuristic · Sonnet
Rewrite `sync_coros_runs` to ~a third of its length:
1. `fetch_unsynced_coros_runs` (lean). Empty → say so, stop. Relay `warning`.
2. Show one line per run: `#pending_id · date · km · pace · → suggested shoe (reason)`; flag null/refreshed suggestions as "pick one". Use `rotation` for names — **don't** call `get_owned_shoes`.
3. Wait for the reply (INV-8). Accept "all good", per-run overrides by shoe name, skips, dismissals.
4. One `confirm_pending_coros_runs` call. Report `per_shoe`, `thresholds` (offer deals/notes), `errors` verbatim. Skipped runs stay pending.
- **Remove the pace/distance bands** from the prompt. Claude starts from `suggestion_reason`; it may differ only with a stated reason.
- `coros_suggestion.py` docstring: drop "two renderings of one rule — change both"; the service is now the only rendering.
- `design_decisions.md`: new entry (next C-number) — "sync prompt no longer restates the suggestion heuristic; server suggestion is the single source; batch confirm by pending_id is the MCP default." Reference C9/INV-8 unchanged.

Tests: update `test_prompt_uses_the_queue_not_the_connector_for_logging` (expects `confirm_pending_coros_runs`, not `get_owned_shoes`); keep `test_prompt_thresholds_generated_from_table`; add a guard `len(prompt) < 2500` so it doesn't regrow.

### T6 — Son of Anton check · Haiku
Son of Anton consumes the same MCP server in-process (C14). Grep `chat_service` / its system prompt and tool allowlist for `confirm_coros_run` / `get_owned_shoes` sync instructions; switch to the batch tool if listed. Verify in the app chat: "sync my runs" → one fetch, one batch confirm. If there's no allowlist, record "no change needed" in the changelog.

### T7 — (optional) "Confirm all suggestions" in the New runs inbox · Sonnet
Frontend: button on the inbox that confirms every run with a non-null suggestion via `POST /pending/resolve`, behind a confirmation dialog listing them (destructive-action rule, §7). `api.js` → `useApi.js` hook invalidating the pending + owned-shoes query keys. Desktop + ~380 px pass, 0 console errors. Skip if the per-run tap is fine in practice.

### T8 — S13 wrap-up · Haiku
Changelog entry (with suite count, before/after tool-call count for a sample N-run sync), `project_state.md` refresh, move findings into `design_decisions.md`, **delete this file**.

---

## §2 Invariant checklist (reviewer)
- INV-1/INV-2: only `coros_inbox.confirm` → `coros.confirm_run` → `rotation.log_run` writes; T2 adds no write path.
- INV-5: batch re-run is a no-op (test).
- INV-7: refreshed suggestions are never persisted.
- INV-8: no default-to-suggestion; `owned_shoe_id` explicit per item; prompt still waits for the reply.
- No schema change → no migration. If one sneaks in, it's out of scope.

## §3 Parked (not this phase)
**History-learned suggestions** (score runs against each shoe's own pace/distance/focus profile instead of fixed bands). Behaviour change, so it goes separately (§11: don't change storage/behaviour with plumbing).
*Step 0 before building:* measure the override rate — confirmed `shoe_runs.owned_shoe_id` vs `pending_coros_runs.suggested_shoe_id` for confirmed rows. Build only if the runner overrides often enough to matter. Gate it the way R6.4 is gated.
