# Skill S01 — add-service-capability *(the master workflow)*

## Purpose
The end-to-end workflow for adding a new capability: service function → tests → REST endpoint
→ MCP tool → (optional) UI. Most other skills are steps of this one.

## When to use
Any feature that adds *behavior*, not just presentation. If the request is
"Anton should be able to X," start here.

## Required context
- `CLAUDE.md` §§2–4 (philosophy, folders, architecture principles) and §6 (patterns + traps).
- `docs/architecture.md` §7–§9 (services, API patterns, AI layer).
- `docs/domain_model.md` §4–§5 — does an invariant or sanctioned write path already own this?
- `CLAUDE.md` §14 (Invariants) — check nothing you're about to build violates the list.

## Workflow
1. **Locate the owning domain** and read `domain_model.md` §5 (ownership boundaries). If a
   sanctioned write path already covers this (`rotation.log_run`, `DealStore`), *extend it*
   with the escape-hatch pattern (CLAUDE.md §6) — never add a parallel path.
2. **Write the service function** — session-first signature, keyword-only options, dataclass
   result, docstring stating commit ownership (CLAUDE.md §5–§6).
3. **Tests for the rule and its boundaries** (skill S09) — *before* any adapter.
4. **Thin REST endpoint** (skill S02).
5. **Matching MCP tool** (skill S06) — REST/MCP parity is mandatory, not optional (CLAUDE.md §4.2).
6. **UI if applicable** (skill S08).
7. **Wrap up** (skill S13).

## Common mistakes
- Logic in the router "just for now" (the fat-router anti-pattern is flagged debt, not precedent).
- Skipping the MCP twin.
- Recomputing a derived value client-side (violates CLAUDE.md §2.1 / design_decisions A4).
- A new write path instead of a parameter on the existing one (violates CLAUDE.md §14 INV-2).
- Forgetting both surfaces must show *identical* numbers.

## Checklist
- [ ] Service has sole ownership of the rule
- [ ] Tests green before adapters were written
- [ ] REST + MCP return the same shapes and numbers
- [ ] Docstrings state commit ownership
- [ ] Session wrapped per S13 (changelog entry etc.)
