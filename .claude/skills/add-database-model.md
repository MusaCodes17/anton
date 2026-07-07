# Skill S03 — add-database-model

## Purpose
Add or alter a table/column with the schema disciplines intact.

## When to use
Any change to `backend/app/models/models.py`. For migrations that *move or restructure data*,
this skill is not enough — use S04 (`data-migration.md`).

## Required context
- `CLAUDE.md` §9 (Database Conventions) — read in full, it is short.
- `/project:migrate` command (`.claude/commands/migrate.md`) for the mechanics.
- `docs/design_decisions.md` A6 (dual schema authority caveat) and B13 (derived-never-stored).
- `docs/domain_model.md` §7.2 (naming: units in names, `*_at` vs `*_date`, lowercase status enums).

## Workflow
1. **Model change** — docstring states the *domain meaning*, not the columns; units in names;
   server-side stamps (`server_default=func.now()`), never client-supplied.
2. **Schema change** in `models/schemas.py` (Pydantic only at the boundary).
3. `alembic revision --autogenerate` → **prune autogenerate noise** (SQLite type-mapping
   artifacts) → review the batch-mode output (`render_as_batch=True`).
4. Apply the migration to the live DB. Never rely on `create_all` to apply it (A6: it only
   creates *missing tables* — a model edit without a migration silently diverges on the real DB).
5. Update `models/__init__.py` exports if the façade is in use; match the file's import style.
6. Tests touching the new shape (S09).
7. New entity? Add its row to the `docs/architecture.md` §5 schema table.

## Common mistakes
- Relying on `create_all` to apply the change (see step 4).
- Storing a derived value (B13; the blessed exceptions are listed in CLAUDE.md §9 and §14 INV-7).
- Client-suppliable audit fields.
- Missing the second side of a relationship (`back_populates`) or its cascade intent.
- Forgetting the `models/__init__` façade export.

## Checklist
- [ ] Migration exists and applies cleanly to the live DB
- [ ] Autogenerate noise pruned
- [ ] Naming conventions held (units, `*_at`/`*_date`, plural snake_case)
- [ ] `alembic downgrade -1` at least drops cleanly for additive changes
- [ ] `architecture.md` §5 updated if a new entity
- [ ] Wrap up per S13
