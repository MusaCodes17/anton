Close out a session cleanly by running the S13 session-wrapup skill. Use this at
the end of any session that did **not** go through `/project:phase` (which
already runs S13 as its final step). It keeps the documentation system truthful:
changelog entry, project_state refresh, design_decisions updates, roadmap row
moves, and the closing commits.

## Steps

1. Invoke the `session-wrapup` skill (`.claude/skills/session-wrapup.md`, S13)
   and follow it verbatim — it is the authoritative ritual; this command only
   points at it.
2. Work the CLAUDE.md "Session Checklist" in order: suite green (record count);
   `vite build` clean + 0 console errors + desktop/~380 px pass for any UI work;
   migration written for any schema change.
3. Append the dated changelog entry at the **top** of `docs/changelog.md`
   (`[ADDED]/[CHANGED]/[REMOVED]/[BLOCKED]`, what / why / how-verified).
4. Refresh `docs/project_state.md` (snapshot date, §2, §9, §11); update
   `docs/design_decisions.md` for any decision made or reversed; move shipped
   roadmap rows per the roadmap maintenance note.
5. Commit the doc edits with the code they describe — one commit per task.

## Required files to read first
- `.claude/skills/session-wrapup.md` (the skill this command runs)
- `CLAUDE.md` "Session Checklist" + §13
- top 2–3 entries of `docs/changelog.md` (format exemplar)

## Output / success criteria
- Every CLAUDE.md Session Checklist item satisfied.
- Changelog entry added; project_state, design_decisions, roadmap current.
- Session's doc edits committed alongside their code.
