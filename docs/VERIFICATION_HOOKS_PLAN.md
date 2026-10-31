# R13 — Verification hooks for Claude Code sessions (plan)

**Status:** planned 2026-10-31, not started. In-flight plan doc (CLAUDE.md §3): when it ships, move lasting findings into `design_decisions.md` + a CLAUDE.md note and delete this file.
**Commit prefix:** `r13:` · one commit per numbered task · ends with S13 wrap-up.
**Complexity:** Low–Medium (one session). Local developer tooling only: no app code, no schema, nothing deployed.

---

## §0 Why

Today, correctness is checked by (a) the subagent running tests if it remembers to, (b) the orchestrator reading diffs, and (c) CI after push. (b) is the expensive one. The orchestrator spends tokens reasoning about whether code works, which is a question a machine can answer for free.

Hooks give every session (main and subagent) a **deterministic pass/fail signal** in the loop:
- **Silent on success.** A passing check prints nothing, so it costs no context. On failure Claude sees only the tail of the output (`--tb=short`, last ~40 lines).
- The orchestrator's review narrows to *does this meet the requirements and CLAUDE.md*, not *does it run*.
- CI (`ci.yml`) stays the merge gate. Hooks just catch failures before the push.

**Not in scope:** replacing CI; frontend lint (eslint isn't installed; adding it is a separate decision); the manual visual pass (§10, stays manual).

## §1 Facts the design depends on

- Hook spec (code.claude.com/docs/en/hooks): `PreToolUse` can block (exit 2 or `permissionDecision`); `PostToolUse` can't block but exit 2 shows stderr to Claude; `Stop`/`SubagentStop` exit 2 or `decision: "block"` keeps Claude working; `async` / `asyncRewake` (background, wakes Claude on exit 2); default command timeout 600 s; matchers like `Edit|Write`.
- **Worktrees are in use** (`.claude/worktrees/`). `$CLAUDE_PROJECT_DIR` stays at the main checkout even inside a worktree, so scripts must take the directory to check from the input JSON `cwd` (→ `git rev-parse --show-toplevel`). The venv lives only in the main checkout, so run `$CLAUDE_PROJECT_DIR/backend/venv/bin/python` against the worktree's `backend/`.
- Tests must not need `.env` (§10). Hooks inherit that: run pytest exactly as CI does.
- `.claude/settings.local.json` is a personal permissions file. Hooks go in **`.claude/settings.json` (committed)** so every session and worktree gets them.

---

## §2 Tasks

Model hints are for /orchestrate. Opus reviews every diff.

### T0 — Step 0: measure · Haiku
Time `python -m pytest -q` (full) and the 5 slowest modules (`--durations=0`, roll up per file). Record the numbers in the changelog draft. **Decision rule:** if the full suite is under ~60 s, the Stop hook runs it in full. Otherwise Stop runs affected modules only, and the full suite moves to `/project:wrapup` + CI.

### T1 — Shared helper `.claude/hooks/_lib.py` · Sonnet
Stdlib-only Python (no venv needed to *run* the hook):
- `read_input()` → parsed stdin JSON.
- `repo_root(cwd)` via `git rev-parse --show-toplevel`.
- `changed_files(root)` → tracked diff vs `HEAD` + untracked (`git status --porcelain`).
- `affected_tests(root, files)` → test modules for changed backend files: (1) `tests/test_<stem>*.py`; (2) any test that imports the module (grep `app.services.<stem>` / `from app.services import ... <stem>`). **Full suite** when a "core" file changed: `models/models.py`, `database.py`, `tests/conftest.py`, `requirements.txt`, `alembic/**`.
- `diff_fingerprint(root)` → hash of `git diff HEAD` + untracked contents. A state file `.claude/hooks/.state/<fingerprint>.ok` means "this exact tree already passed". Skip re-running. Gitignore `.state/`.
- `fail(msg)` → print tail to stderr, exit 2. `ok()` → exit 0, no output.

### T2 — PostToolUse: fast per-edit checks · Sonnet
Matcher `Edit|Write|MultiEdit|NotebookEdit`, script `post_edit.py`, timeout 30 s, synchronous:
- `backend/**.py` → `py_compile` the file (syntax errors caught right away).
- `frontend/src/{components,pages}/**.jsx` → flag hard-coded hex colours (`#[0-9a-fA-F]{3,8}\b` outside comments), per CLAUDE.md §5 design-token rule.
- `backend/app/models/models.py` → non-blocking reminder on stderr, exit 0: "schema change ⇒ Alembic migration (§9)". The Stop hook enforces it.

Second PostToolUse entry, same matcher, **`asyncRewake: true`**, script `post_edit_tests.py`: runs `affected_tests` for the edited file in the background. It only wakes Claude on failure, so a passing run costs nothing and edits never wait on pytest.

### T3 — PreToolUse guards · Sonnet
Script `pre_guard.py`. Use `permissionDecision: "ask"` (you decide) unless it says *deny*:
- **Edit/Write** to `backend/.env*`, `**/*.db*`, `~/anton-data/**` → **deny** (secrets; the live DB is never edited as a file).
- **Edit** of an `alembic/versions/*.py` that already exists on `origin/main` → **ask**. Applied migrations are history; write a new one.
- **Bash** touching `anton-data/shoe_deals.db` with a write verb (`DELETE|UPDATE|INSERT|DROP|ALTER|REPLACE` or `sqlite3` without `-readonly`) → **ask**. Training history is sacred (§2.6). The allowlist currently has `Bash(sqlite3 *)`, and this closes that gap.
- **Bash** `pip install` naming `starlette|fastapi|sse-starlette|mcp` → **ask** (pinned trio, §6 known trap).
- **Bash** `alembic downgrade` → **ask**.

### T4 — Stop gate · Sonnet
Script `stop_gate.py`, matcher none, timeout 600 s:
1. Loop guard: if the input says a stop hook is already active, or this fingerprint has already failed twice (`.state/<fp>.fail` counter), exit 0 and print a one-line `systemMessage` "verification still failing — see last output", so Claude never loops forever.
2. No changes, or fingerprint already `.ok` → exit 0.
3. Backend files changed → pytest (full or affected, per T0). Failure → `decision: block` with the tail.
4. **Test count guard:** parse `N passed` and compare it with `.state/last_count`. If it drops, block: "suite count fell from X to Y (§10: a session that lowers it isn't done)". Allow it if the diff deletes a test module (removed features take their tests with them).
5. `models/models.py` changed and no new file under `alembic/versions/` → block (§9).
6. Frontend files changed → `npm run build` (in the worktree's `frontend/`; skip with a note if `node_modules` is missing there).
7. All pass → write `.ok` + `last_count`, exit 0 silently.

### T5 — SubagentStop gate · Sonnet
Same script with a `--scope affected` flag: affected tests + py_compile + the migration check, **never** the full suite or vite build. Each orchestrated subagent then returns either green or a concrete failure it already tried to fix, and the orchestrator only re-runs the full gate at its own Stop. Reuses the fingerprint cache, so a tree that a subagent already proved green isn't re-tested.

### T6 — Wire up `.claude/settings.json` · Haiku
```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write|MultiEdit|Bash",
        "hooks": [{ "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/pre_guard.py\"", "timeout": 10 }] }
    ],
    "PostToolUse": [
      { "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/post_edit.py\"", "timeout": 30 },
          { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/post_edit_tests.py\"", "asyncRewake": true }
        ] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/stop_gate.py\"", "timeout": 600 }] }
    ],
    "SubagentStop": [
      { "hooks": [{ "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/stop_gate.py\" --scope affected", "timeout": 300 }] }
    ]
  }
}
```
Add `.claude/hooks/.state/` to `.gitignore`. Confirm the hooks load with `/hooks` in a fresh session.

### T7 — Tests for the hooks · Sonnet
`backend/tests/test_claude_hooks.py` (it runs in CI too, so the hooks can't silently rot). Feed each script fixture stdin JSON in a temp git repo:
- Pre-guard: `.env` edit → deny; `sqlite3 ~/anton-data/shoe_deals.db "DELETE …"` → ask; `pytest` → allow; editing a migration present on main → ask.
- `affected_tests` mapping: a services file → its module + importers; `models.py` → full.
- Stop gate: unchanged fingerprint → no pytest run; loop guard stops after 2 failures; count drop blocks; count drop with a deleted test module passes; models change without a migration blocks.
Stub the pytest call (monkeypatch the runner), so these tests take milliseconds.

### T8 — Docs + S13 wrap-up · Haiku
- CLAUDE.md §10: one paragraph, "Local verification hooks (`.claude/settings.json`) run affected tests after edits, guard the live DB/migrations/pins, and gate Stop/SubagentStop. They are a pre-CI convenience; CI remains the merge gate." Plus the escape hatch: `/hooks` to inspect, `disableAllHooks` in `settings.local.json` for a one-off.
- `design_decisions.md`: entry for "hooks are local, silent on success, CI stays authoritative".
- Changelog with T0 timings + suite count, `project_state.md`, **delete this file**.

---

## §3 Review checklist
- Every hook prints **nothing** on success (check with a passing edit in a live session).
- No hook writes to the repo outside `.claude/hooks/.state/`.
- Worktree session: hooks resolve the worktree's root, not `$CLAUDE_PROJECT_DIR`, for what they check.
- Loop guard proven (T7) before T6 wiring is merged.
- Nothing weakens CI or the confirmation gate. These are developer guards only.

## §4 Parked
- **eslint for the frontend.** `lint` script exists, eslint not installed (`ci.yml` comment). Add it as its own decision, then a PostToolUse entry.
- **Prompt/agent-type Stop hook** checking the diff against the active plan doc's acceptance criteria. Revisit after a few sessions show whether Opus review still misses requirement gaps once the mechanical checks are automated.
