Run pending database migrations for the running-shoe-deals backend.

Migrations are now managed by **Alembic** (adopted 2026-07-02). The old ad-hoc `migrate_add_*.py` scripts have been moved to `backend/legacy_migrations/` and should not be run.

---

## Check current migration state

```bash
cd /Users/musasouled/workspace/claude-code/running-shoe-deals/backend
source venv/bin/activate
alembic current          # shows current revision
alembic history --verbose  # shows full revision history
```

## Apply pending migrations

```bash
cd /Users/musasouled/workspace/claude-code/running-shoe-deals/backend
source venv/bin/activate
alembic upgrade head
```

## Add a new column (standard workflow)

1. Add the column to the model in `app/models/models.py`
2. Add the field to the relevant schema in `app/models/schemas.py`
3. Generate a migration:
   ```bash
   alembic revision --autogenerate -m "add_<feature>"
   ```
4. Review the generated file in `alembic/versions/` — autogenerate can include
   noise from SQLite type-mapping differences (REAL vs Float, TEXT vs String).
   Keep only the intentional schema changes; delete the type-coercion noise.
5. Apply it:
   ```bash
   alembic upgrade head
   ```
6. Restart the backend.

## Stamp an existing DB at a revision (no DDL run)

```bash
alembic stamp <revision_id>
```

Used when a DB was already at the right schema before Alembic was introduced
(what we did for the baseline `cf1eccba0a79`).

## Revisions

| ID | Description |
|----|-------------|
| `cf1eccba0a79` | Baseline — existing DB state when Alembic was adopted |
| `6c68ff4148ff` | Add `mileage_limit` (nullable Float) to `owned_shoes` |
