# Skill S06 — add-mcp-tool

## Purpose
Extend the MCP surface (tool, resource, or prompt) keeping REST/MCP parity and the
LLM-facing contract right.

## When to use
Alongside every S01 capability; or when the assistant "can't see/do" something REST can.

## Required context
- `docs/architecture.md` §9 (the AI layer).
- `mcp_server/` exemplars (domain modules `deals`, `shoes`, `coros`, `training`, `onboarding`): a read tool, a `{"success": ...}` write tool, a templated resource.
- `CLAUDE.md` §13 — the docstring *is* the LLM-facing contract.
- `docs/dependency_graph.md` §3 (what the module already imports).

## Workflow
1. **Confirm the service function exists** — never put logic in the tool
   (the 600/700/800 km nudge now lives in `rotation.log_run`; don't add adapter-owned rules).
2. Put the tool in the matching domain module under `backend/app/mcp_server/` and add it to the re-export list in `mcp_server/__init__.py`. Tool body uses `_core.get_session()` (a context manager) — FastAPI DI does **not** work here; tests patch `app.mcp_server._core.get_session`.
   Render ORM results through the shared Pydantic schemas (`app.models.schemas`) where one exists, not a new hand-written dict.
3. **Docstring written for the model**: args, semantics, side effects, and whether human
   confirmation is required (design_decisions C9).
4. Envelope conventions (CLAUDE.md §6): write tools return `{"success": bool, ...}` and never
   raise raw; read tools return plain data; resources return markdown *with* embedded JSON.
5. `ctx.log` for advisory notifications that should reach the client
   (mileage thresholds, scrape completion — CLAUDE.md §8).
6. **Verify** via Son of Anton — tools auto-discover over the loopback MCP client; if chat
   can't see it, the server didn't register it. Verify via Claude Desktop if templated
   resource URIs are involved.

## Common mistakes
- Business logic in the tool body.
- Raising instead of returning `{"success": False, "error": ...}`.
- A docstring written for humans that leaves the model guessing parameter semantics.
- Forgetting resources are pre-primed into chat context (design_decisions C4) — shape changes
  ripple into the system prompt's trust rules.
- Assuming FastAPI dependency injection works in MCP tools (it doesn't — `get_session()`).

## Checklist
- [ ] Logic lives in a service
- [ ] Envelope convention held
- [ ] Docstring answers "should the model call this, and how"
- [ ] Discovered automatically in Son of Anton
- [ ] Parity noted in the changelog entry (S13)
