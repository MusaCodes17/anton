# Skill S02 — add-api-endpoint

## Purpose
Add a REST endpoint the project way — thin, typed, derivations attached at the boundary.

## When to use
New route over existing/new service logic; also when converting a fat-router pattern
(that conversion itself follows S10).

## Required context
- `CLAUDE.md` §4.1 (thin adapters) and §7 (error translation).
- Exemplars: `routers/races.py` (thin CRUD) or `routers/home.py` (aggregate-per-page).
- `models/schemas.py` conventions.

## Workflow
1. Pick the router file by resource (one file per resource — CLAUDE.md §3).
2. Handler with `Depends(get_db)`; **delegate to the service** — the handler translates, never decides.
3. Pydantic response model (`from_attributes` if reading boundary-attached fields).
4. Error translation: `LookupError → 404`, `ValueError → 400/502` (502 for upstream),
   `RequestException → 502`, scrape-in-progress → `409` (CLAUDE.md §7).
5. Register the router in `main.py` if new.
6. Endpoint-level tests (S09).
7. If it will be consumed by the SPA: client function in `frontend/src/services/api.js`
   (then S08 for the hook/page). **Trap:** router prefixes ↔ `api.js` paths are hand-matched
   strings — grep the other side on any rename (CLAUDE.md §6).

## Common mistakes
- Aggregation loops in the handler — the `watchlist` anti-pattern is flagged debt (tech_debt
  P1-10), not precedent to copy.
- Returning bare ORM objects where a schema exists.
- Inventing a second error shape.
- Missing the `/` vs no-slash double-decorator convention where used (`races.py`).
- Adding an endpoint the MCP surface can't mirror — that means the logic is in the wrong layer.

## Checklist
- [ ] Handler ≤ ~15 lines
- [ ] Response model (or documented shaped dict)
- [ ] Errors translated, not leaked
- [ ] Appears in the OpenAPI docs
- [ ] A test hits it · wrap up per S13
