# Skill S06 — add-mcp-tool

## Purpose
Extend the MCP surface (tool, resource, or prompt) keeping REST/MCP parity and the
LLM-facing contract right.

## When to use
Alongside every S01 capability; or when the assistant "can't see/do" something REST can.

## Required context
- `docs/architecture.md` §9 (the AI layer).
- `mcp_server.py` exemplars: a read tool, a `{"success": ...}` write tool, a templated resource.
- `CLAUDE.md` §13 — the docstring *is* the LLM-facing contract.
- `docs/dependency_graph.md` §3 (what the module already imports).

## Workflow
1. **Confirm the service function exists** — never put logic in the tool
   (mcp_server.py's embedded rules are flagged debt, tech_debt P1-6; don't add more).
2. Tool body uses the `get_session()` context manager — FastAPI DI does **not** work here.
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
