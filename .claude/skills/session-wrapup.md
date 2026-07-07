# Skill S13 — session-wrapup

## Purpose
The end-of-session ritual that keeps the documentation system alive (roadmap R5.6's engine).
Every other skill ends by pointing here. The session isn't done until this is done.

## When to use
Every working session, last ~10 minutes — regardless of what the session did.

## Required context
- `CLAUDE.md` — "Session Checklist" (the authoritative list) and §13 (Documentation Standards).
- `docs/project_state.md` maintenance note (bottom of file): what to refresh and how it decays.
- The top 2–3 entries of `docs/changelog.md` as the format exemplar — match their voice and structure.

## Workflow
1. **Suite green** — run the full pytest suite; record the count (the live count is authoritative
   only in the newest changelog entry and `project_state.md` §2 — see CLAUDE.md §10).
2. **UI work?** — `vite build` clean, 0 console errors, desktop + ~380 px pass. State the pass explicitly.
3. **Changelog entry** at the *top* of `docs/changelog.md`: dated title, `[ADDED]/[CHANGED]/[REMOVED]/[BLOCKED]`
   tags, what / why / how-verified (test counts, reconciliation numbers, viewport passes).
4. **`docs/project_state.md` refresh:** snapshot date, §2 status table, §9 recent decisions,
   §11 priorities; move shipped §4/§5 items into §3.
5. **`docs/design_decisions.md`** if a decision was made or reversed — reversals get a
   Superseded entry naming the successor, in the *same session* (CLAUDE.md §11).
6. **Roadmap** — if an R-item shipped, move its row into project_state §3 and note it in the
   roadmap per its maintenance note.
7. **Commits:** one per numbered task, phase-prefixed (`r1:`, `p5:` — see roadmap Naming note).

## Common mistakes
- The entry says *what* but not *how verified* — counts, reconciliations, and viewport passes
  are the entry's spine, not decoration.
- Updating the changelog but not `project_state.md` (which decays fastest of all docs).
- Shipping a decision reversal without its Superseded entry.
- Batching a week of work into one commit.

## Checklist
- [ ] CLAUDE.md "Session Checklist" — every item, verbatim
- [ ] Roadmap rows current (shipped items moved)
- [ ] This session's doc edits committed *with* the code they describe
