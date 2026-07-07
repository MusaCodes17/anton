# Skill S09 — write-tests

## Purpose
What deserves tests here, and the house style for writing them:
**test the rules, not the plumbing.**

## When to use
Every S01–S06 flow; standalone whenever an invariant (CLAUDE.md §14) is touched.

## Required context
- `CLAUDE.md` §10 (Testing Expectations) — read in full.
- Exemplars: `tests/test_rotation_overview.py` (boundary style), `tests/test_home.py`
  (aggregate style), `tests/conftest.py` (fixtures — reuse them).
- `CLAUDE.md` §14 — which invariants have coverage and which are marked "no test".

## Workflow
1. **Identify the rule** the change encodes — that's what gets tested, not the ORM mechanics.
2. **Name boundary cases explicitly** as their own tests: exactly 75% is *in* the pipeline;
   empty week reads 0; race-today = 0 days; case-insensitive type matching.
3. **Invariant round-trips when touched**: log + delete restores mileage; double-confirm is
   a silent no-op; archive rows survive attribution deletion.
4. Endpoint tests for new routes (backend + tests land *before* the consuming UI task —
   standing rule, CLAUDE.md §10).
5. Run the full suite; record the count for the changelog (live count is authoritative in the
   newest changelog entry and `project_state.md` §2 only).
6. Removed features take their tests with them (the `strava_backfill` precedent).

## Common mistakes
- Testing that SQLAlchemy works.
- Skipping the boundary that the code comment says matters.
- HTML-fixture tests for retailer DOMs — use the dry-run endpoints instead (documented decision).
- Letting the suite count silently drop — a session that lowers the number isn't done.
- Asserting on formatting when the rule is numeric (test seconds/km, not `"M:SS"` strings).

## Checklist
- [ ] Rules and boundaries covered
- [ ] Suite green, count noted for the changelog
- [ ] No scraper DOM fixtures
- [ ] Fixtures reused from `conftest.py` · wrap up per S13
