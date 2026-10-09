# docs/archive — retired documents

Files here are **superseded and must not be followed**. They are kept for history only (git-tracked moves preserve blame/log).

| File | Archived | Why |
|---|---|---|
| `TROUBLESHOOTING.md` | 2026-07-13 | Pre-Alembic era. References `seed_data.py`, `run.py`, in-repo `venv/`, and `shoe_deals.db` in the working tree; advises deleting/reseeding the DB — all of which contradict R2.2 (Alembic sole schema authority, `create_all` test-only, live DB in `~/anton-data/`) and would be destructive if followed today. |
| `QUICKSTART.md` | 2026-07-13 | Same era; "7 retailers / 12 shoes" seed setup, `0.0.0.0` bind with no auth (contradicts R2.1/E9), no mention of OAuth, Docker, or `~/anton-data/`. Current setup lives in `CLAUDE_DESKTOP_SETUP.md`, `docker-compose.yml`, and `deploy/`. |
| `REMOTE_ACCESS_PLAN.md` | 2026-10-09 | RA1 and RA2 shipped (cutover closed; OAuth, session auth, PWA live). The one open RA item, RA3 push-to-deploy, is scoped in `roadmap.md` §RA3. Still the record for the D0 hosting decision and the RA1 runbook (§6/§7). |
| `RA2_2_PWA_PLAN.md` | 2026-10-09 | RA2.2 shipped 2026-08-31. §6 (the deferred offline write-queue) stays the reference for that gated item (E11). |
| `MAINTENANCE_PLAN.md` | 2026-10-09 | Every urgent, defect and housekeeping row is done (RA1.5 cutover included); the leftovers (T1 `mcp_server.py` size, T2 dual serialization, T10 proxy trap) are tracked in `refactoring/tech_debt.md`. |
| `documentation_review.md` | 2026-10-09 | A dated July review of the docs suite; its recommendations were applied or superseded. |
| `skills_library.md` | 2026-10-09 | The design for the 13 skills; all are implemented under `.claude/skills/`, which are now the source of truth. |
| `ai_context.md` | 2026-10-09 | The "read this first" orientation index, last refreshed 2026-07-14 (suite 64); it had drifted badly. `CLAUDE.md` + `project_state.md` + `roadmap.md` now do that job. |

Completed execution plans (`REDESIGN_PLAN.md`, `SECURITY_PASS_PLAN.md`, `TRAINING_DEPTH_PLAN.md`, `CHAT_PERSISTENCE_PLAN.md`, `REFACTOR_PLAN.md`, `UI_REVIEW_TASKS.md`, `STRAVA_IMPORT_REVIEW_TASKS.md`, `strava-historical-import-plan.md`, `documentation_creation.md`) were **moved here from the repo root on 2026-07-14 (task H2)** after a cross-reference sweep updated every path citation in the living docs. They are historical-but-accurate append-only plans — read for context, not as current instructions. Live outside the archive: `CLAUDE.md` (root), and in `docs/` the core suite plus `CLAUDE_DESKTOP_SETUP.md` and `spikes/`.

Note: append-only history that references these plans by their old root path — the `docs/changelog.md` session entries and the dated `docs/documentation_review.md` deliverable — was **deliberately not rewritten** (CLAUDE.md §13: don't rewrite shipped history); those mentions are names, not live navigation.
