# Skill S04 — data-migration *(the E4 bar)*

## Purpose
The heavyweight discipline for migrations that *move or restructure data*. The live DB is the
only DB (design_decisions A1) — there is no staging to save you.

## When to use
Any migration beyond additive columns: table merges/splits, backfills, data rewrites.
(Additive-only changes: S03 suffices.)

## Required context
- `docs/design_decisions.md` E4 (the bar) + B4/B5 (the worked example and its trade-offs).
- `alembic/versions/c3d4e5f6a7b8_canonical_activities.py` — the reference implementation;
  `d4e5f6a7b8c9_msrp_drives_deals` is the second worked example.
- `CLAUDE.md` §9 (conventions) and §11 (never refactor storage and behavior in the same change).

## Workflow
1. **Write a §-plan first**: what moves, what's invariant, what's the observable contract
   (e.g. "counters untouched, response shapes identical").
2. **Pre-migration backup**: `shoe_deals.db.bak-<name>` (named, dated by the changelog entry).
3. Reversible `upgrade`/`downgrade` — both, always.
4. **Reconciliation queries defined *before* running** (counts, sums, per-entity drift).
5. Run on the live DB → reconcile pre/post exactly.
6. `downgrade -1` round-trip test (yes, even though "we'll never roll back").
7. Suite green; UI spot-check the affected pages.
8. Changelog entry records *all* the numbers (S13).

## Common mistakes
- Irreversible downgrade — the reference migration proved you test the round trip anyway.
- Reconciling after the fact instead of defining the checks before.
- Changing behavior in the same change as storage (CLAUDE.md §11 rule).
- Skipping the backup because "it's quick."
- Not stating the invariant contract, so nobody can verify it held.

## Checklist
- [ ] Plan doc / § entry exists
- [ ] Named `.bak` backup exists before the run
- [ ] Downgrade round-trips
- [ ] Reconciliation numbers recorded in the changelog
- [ ] Behavior-preservation contract stated and verified
- [ ] Wrap up per S13
