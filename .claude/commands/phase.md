Execute a named roadmap phase end to end — the replacement for the manual
handover prompt. Invoked as `/project:phase <name>` (e.g. `/project:phase r2.2`).
Claude orients, finds the phase in the roadmap, reads its plan doc and skills,
then executes the phase's tasks in order, committing after each, and closes with
the session-wrapup skill.

## Steps

1. Read `docs/ai_context.md`, `CLAUDE.md`, and `docs/project_state.md` to orient.
2. Read `docs/roadmap.md`; find the named phase's entry (the `<name>` argument,
   case-insensitive). If it isn't there, stop and say so.
3. Read any relevant root plan doc for that phase (e.g. `SECURITY_PASS_PLAN.md`
   for R2.1). If none exists, derive the task list from the roadmap entry.
4. Read the skill files the phase's tasks require (`.claude/skills/*.md`).
5. Execute the phase tasks **in order**, one phase-prefixed commit per numbered
   task (`r2:`, `p5:` — see roadmap Naming note). Suite must stay green.
6. End with the `session-wrapup` skill (S13) — changelog, project_state, roadmap
   row moves, design_decisions updates.

## Required files to read first
- `docs/ai_context.md`, `CLAUDE.md`, `docs/project_state.md`
- `docs/roadmap.md` + the phase's plan doc
- the `.claude/skills/*.md` files the phase touches

## Output / success criteria
- Every task in the phase's plan is done and committed (one commit per task).
- Full pytest suite green; UI bar met if the phase touched the frontend.
- S13 ran: changelog entry, project_state refreshed, roadmap row moved.
