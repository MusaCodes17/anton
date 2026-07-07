# Skill S10 — refactor-service

## Purpose
Restructure safely: seams, compatibility shims with expiries, behavior-preservation contracts.

## When to use
Extracting logic from fat adapters; changing internals of a shared computation;
retiring flagged debt.

## Required context
- `CLAUDE.md` §11 (Refactoring Philosophy) — the whole section.
- `docs/design_decisions.md` A3, B5, D7, E4.
- `docs/dependency_graph.md` §11 — the standing debt list; **check your target is on it**
  (the drive-by rule: don't refactor mid-feature what isn't in the session's phase).
- `services/activities.py` — the seam as the worked example (two-store union → canonical
  table with zero caller changes).

## Workflow
1. Confirm the target's entry in design_decisions / dependency_graph. If reversing a
   documented decision, prepare its **Superseded** entry now, not later.
2. **Define the observable-behavior contract** ("response shapes identical",
   "numbers unchanged") — before touching code.
3. Build or locate the seam; migrate callers *to* the seam.
4. Swap the internals behind it.
5. **Prove the contract** — tests, reconciliation queries, or both.
6. If a shim was used, add it to the debt list with an expiry (⚠️ verdict in design_decisions).
7. Docs updated in the same session (S13); struck debt rows get changelog pointers.

## Common mistakes
- Behavior and structure in one change (CLAUDE.md §11's hardest rule).
- Refactoring something *not* on the debt list mid-feature.
- Leaving the shim off the debt list — "temporary" without an expiry is immortal.
- Breaking REST/MCP parity by refactoring only one adapter.
- Missing the `models/__init__` / import-convention cleanups named in dependency_graph §11.4.

## Checklist
- [ ] Contract stated before, verified after
- [ ] All callers on the seam
- [ ] Debt list updated (shim added / finished item struck with pointer)
- [ ] design_decisions updated if a decision changed
- [ ] Both API surfaces still agree · wrap up per S13
