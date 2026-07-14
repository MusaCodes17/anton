# docs/archive — retired documents

Files here are **superseded and must not be followed**. They are kept for history only (git-tracked moves preserve blame/log).

| File | Archived | Why |
|---|---|---|
| `TROUBLESHOOTING.md` | 2026-07-13 | Pre-Alembic era. References `seed_data.py`, `run.py`, in-repo `venv/`, and `shoe_deals.db` in the working tree; advises deleting/reseeding the DB — all of which contradict R2.2 (Alembic sole schema authority, `create_all` test-only, live DB in `~/anton-data/`) and would be destructive if followed today. |
| `QUICKSTART.md` | 2026-07-13 | Same era; "7 retailers / 12 shoes" seed setup, `0.0.0.0` bind with no auth (contradicts R2.1/E9), no mention of OAuth, Docker, or `~/anton-data/`. Current setup lives in `CLAUDE_DESKTOP_SETUP.md`, `docker-compose.yml`, and `deploy/`. |

Root-level completed execution plans (`REDESIGN_PLAN.md`, `SECURITY_PASS_PLAN.md`, `TRAINING_DEPTH_PLAN.md`, `CHAT_PERSISTENCE_PLAN.md`, `REFACTOR_PLAN.md`, `UI_REVIEW_TASKS.md`, `STRAVA_IMPORT_REVIEW_TASKS.md`, `strava-historical-import-plan.md`, `documentation_creation.md`) are historical-but-accurate append-only plans; relocating them here is task **H2** in `MAINTENANCE_PLAN.md` (needs a cross-reference sweep first — several are cited by path from `docs/`).
