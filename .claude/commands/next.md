Do the next right thing. This command self-orients, identifies the single
highest-priority task from `docs/project_state.md` §11, loads the matching skill,
and executes it — or, if the task is a multi-session phase, produces a
§-numbered plan and confirms before executing. Use it when you want Anton to
pick up work without a hand-written handover prompt.

## Steps

1. Read `docs/ai_context.md`, `CLAUDE.md`, `docs/project_state.md` **§11**, and
   `docs/roadmap.md` to orient.
2. Identify the **single** highest-priority next task — the first item in
   project_state §11. State it back in one sentence.
3. Match the task to a skill in `.claude/skills/` (e.g. schema work →
   `add-database-model`, endpoint → `add-api-endpoint`, tests → `write-tests`)
   and read that skill file.
4. Decide scope:
   - **Small, single-session task** → execute it now, following the skill.
   - **Multi-session phase** → produce the §-numbered plan and **confirm** with
     the user before writing any code.
5. On completion, run the `session-wrapup` skill (S13) unless the task was
   trivial and the user is mid-flow.

## Required files to read first
- `docs/ai_context.md`, `CLAUDE.md`
- `docs/project_state.md` §11, `docs/roadmap.md`
- the one `.claude/skills/*.md` matching the task type

## Output / success criteria
- The chosen task is named and traced to project_state §11.
- Either the task is done (small) or a confirmed plan exists (phase).
- Work follows the sanctioned skill; no parallel write paths introduced.
