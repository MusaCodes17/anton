# Legacy Migrations

These scripts were the original ad-hoc migration mechanism before Alembic was
adopted. They are kept here for historical reference only — **do not run them**.

The database was bootstrapped by `init_db()` + these scripts. Alembic's baseline
revision (`cf1eccba0a79`) marks the point where Alembic management began. All
future schema changes should be made as Alembic revisions under `backend/alembic/versions/`.

See `backend/README.md` for the Alembic workflow.
