# docs/archive — retired documents

Files here are **superseded and must not be followed**. They are kept for history only (git-tracked moves preserve blame/log).

| File | Archived | Why |
|---|---|---|
| `TROUBLESHOOTING.md` | 2026-07-13 | Pre-Alembic era. References `seed_data.py`, `run.py`, in-repo `venv/`, and `shoe_deals.db` in the working tree; advises deleting/reseeding the DB — all of which contradict R2.2 (Alembic sole schema authority, `create_all` test-only, live DB in `~/anton-data/`) and would be destructive if followed today. |
| `QUICKSTART.md` | 2026-07-13 | Same era; "7 retailers / 12 shoes" seed setup, `0.0.0.0` bind with no auth (contradicts R2.1/E9), no mention of OAuth, Docker, or `~/anton-data/`. Current setup lives in `CLAUDE_DESKTOP_SETUP.md`, `docker-compose.yml`, and `deploy/`. |

Completed execution plans (`REDESIGN_PLAN.md`, `SECURITY_PASS_PLAN.md`, `TRAINING_DEPTH_PLAN.md`, `CHAT_PERSISTENCE_PLAN.md`, `REFACTOR_PLAN.md`, `UI_REVIEW_TASKS.md`, `STRAVA_IMPORT_REVIEW_TASKS.md`, `strava-historical-import-plan.md`, `documentation_creation.md`) were **moved here from the repo root on 2026-07-14 (task H2)** after a cross-reference sweep updated every path citation in the living docs. They are historical-but-accurate append-only plans — read for context, not as current instructions. Still at the repo root: `CLAUDE.md`, `REMOTE_ACCESS_PLAN.md` (live RA runbook), `CLAUDE_DESKTOP_SETUP.md`, `MAINTENANCE_PLAN.md`.

Note: append-only history that references these plans by their old root path — the `docs/changelog.md` session entries and the dated `docs/documentation_review.md` deliverable — was **deliberately not rewritten** (CLAUDE.md §13: don't rewrite shipped history); those mentions are names, not live navigation.
