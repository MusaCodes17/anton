# R15 — Convert `.claude/skills/` into real Claude Code skills (plan)

**Status:** planned 2026-10-31, not started. In-flight plan doc: delete when shipped (findings → `design_decisions.md` + AGENTS.md §3).
**Commit prefix:** `r15:` · one commit per task · Low complexity (one short session). No app code.

## §0 Why
The 13 files in `.claude/skills/` (S01–S13, ~27 KB) are flat `.md` files. Claude Code only discovers skills as `.claude/skills/<name>/SKILL.md` with `name` + `description` frontmatter, so today they load only if a session remembers to read them. AGENTS.md §3 has to tell it to.
Converted, each session loads just the 13 one-line descriptions. A skill's body loads only when its kind of work starts (e.g. adding an MCP tool), and orchestrated subagents get the same discovery.

## §1 Tasks

### T1 — Move + frontmatter · Haiku
For each `<name>.md` → `git mv` to `<name>/SKILL.md` (keeps history). Prepend:
```yaml
---
name: <name>
description: <when to use it, one sentence, ≤ 200 chars — trigger words first>
---
```
Write each description from the file's own "When to use" section. Examples:
- `add-mcp-tool`: "Use when adding or changing an Anton MCP tool, resource or prompt (mcp_server/*): placement, docstring-as-contract, tests patching _core.get_session."
- `data-migration`: "Use before any Alembic migration that moves or reshapes data: E4 bar, backup, reconciliation, reversible downgrade."
- `session-wrapup`: "Use at the end of every working session, or when running /project:wrapup: suite count, changelog, project_state, decisions, roadmap."
Bodies are unchanged except T2's path fixes.

### T2 — Fix references · Haiku
Grep the repo for `.claude/skills/` and `CLAUDE.md` mentions inside the skills, `.claude/commands/*.md`, AGENTS.md, `docs/` and `.claude/hooks/`:
- Old flat paths → `.claude/skills/<name>/SKILL.md`, or better "the `<name>` skill".
- Skills citing "CLAUDE.md §N" → "AGENTS.md §N" (CLAUDE.md is now only `@AGENTS.md`). Spot-check that each cited § number still exists after the 2026-10-31 trim; e.g. `session-wrapup` cites §10, §11, §13 and the Session Checklist.
- Skill cross-references ("every other skill ends by pointing here") keep working by name.

### T3 — AGENTS.md §3 line · Haiku
Replace the "flat reference docs, NOT auto-loaded" line with: `.claude/skills/  13 project skills (S01–S13), auto-discovered; the descriptions say when each applies`.

### T4 — Guard test · Sonnet
`backend/tests/test_claude_skills.py` (runs in CI):
- Every dir under `.claude/skills/` has a `SKILL.md`.
- No stray `.md` sits directly in `.claude/skills/`.
- Frontmatter parses and `name` == dir name; `description` is non-empty and ≤ 1024 chars.
- No skill references a `.claude/skills/*.md` flat path.

Writing this before T1 finishes makes the background test hook fire (red → green), a cheap extra live check for R13 (§3 H3 in the R14 plan).

### T5 — Verify + wrap-up · Haiku
In a fresh session, check that the 13 skills are listed and that one triggers by description: ask "add an MCP tool that returns X" and see that `add-mcp-tool` loads. Then the changelog entry (suite count) and **delete this file**.

## §2 Review checklist
- `git log --follow` works on a moved skill (history kept).
- No skill body changed beyond path/§ fixes.
- No command or hook still points at a flat path.
