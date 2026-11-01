"""Stop / SubagentStop verification gate for Anton's local hooks (phase R13).

Job: before Claude (or a subagent) is allowed to stop, check the working tree
and, on a failure, return ``{"decision": "block", "reason": <output tail>}`` so
Claude keeps working. A pass prints nothing. One script, two scopes:

- ``--scope stop`` (default, the Stop hook): compile check, migration check,
  affected tests (the whole suite only when a core file changed), the suite-count
  guard, and ``npm run build`` when frontend files changed.
- ``--scope affected`` (the SubagentStop hook): compile check, migration check and
  affected tests only. Never the full suite, the count guard or the vite build:
  each worker returns green-or-concrete-failure, and the orchestrator's own Stop
  runs the full gate.

Rationale / constraints:
- Full suite measures 54-68 s (T0), so Stop runs *affected* tests and falls back
  to the whole suite only for a core file (``affected_tests`` returns None).
- Count guard uses ``pytest --collect-only`` (~9 s, always counts the whole
  suite) rather than parsing ``N passed``, which would be a subset count after an
  affected run. The baseline is per branch: switching branches legitimately
  changes the count.
- Fingerprint cache: an unchanged tree that already passed this scope is never
  re-tested. The affected scope records ``<fp>-affected`` so the later Stop does
  not rerun pytest on a tree a subagent already proved.
- Loop guard, three independent limbs (see ``main``). ``stop_hook_active`` alone
  deliberately does NOT stand down: Claude's fix after a block is the very tree
  that most needs verifying, so standing down on the flag would let every fix
  through unchecked.
- Fails open: any unexpected exception prints nothing and returns 0. A gate bug
  must never wedge a session.
- Writes only under ``.claude/hooks/.state/`` (plus gitignored build/pytest caches).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Keep the hook from writing .pyc files for _lib into the repo.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib  # noqa: E402

# Stop scope may run the whole suite (~60 s) plus the count guard (~9 s) and a
# frontend build, inside the 600 s hook timeout; affected scope has 300 s.
STOP_PYTEST_TIMEOUT_S = 540
AFFECTED_PYTEST_TIMEOUT_S = 270
COUNT_TIMEOUT_S = 120
BUILD_TIMEOUT_S = 240

# Cap on back-to-back blocks while Claude keeps "fixing" (a changing tree defeats
# the per-fingerprint counter, so this bounds an endless series).
MAX_CONSECUTIVE_BLOCKS = 4

STAND_DOWN_MSG = "verification still failing — see last output"

# A models.py line matching this is a schema change; comments/docstrings are not.
SCHEMA_LINE_RE = re.compile(
    r"Column\(|mapped_column\(|__tablename__|ForeignKey\(|Index\(|"
    r"UniqueConstraint\(|CheckConstraint\("
)
MODELS_PATH = "backend/app/models/models.py"
MIGRATIONS_RE = re.compile(r"^backend/alembic/versions/[^/]+\.py$")


# --------------------------------------------------------------------------
# Slow steps: module-level so tests can stub them
# --------------------------------------------------------------------------

def run_pytest(py: Path, tests: list[str] | None, backend_dir: Path,
               timeout: int) -> tuple[int, str]:
    """Run pytest; ``tests=None`` means the whole suite."""
    cmd = [str(py), "-m", "pytest", "-q", "--tb=short", "--disable-warnings", *(tests or [])]
    return _lib.run(cmd, backend_dir, timeout=timeout)


def count_tests(py: Path, backend_dir: Path) -> int | None:
    """Number of tests in the whole suite via ``--collect-only -q``, or None if
    it can't be determined (the count guard is then skipped)."""
    code, out = _lib.run(
        [str(py), "-m", "pytest", "--collect-only", "-q"], backend_dir,
        timeout=COUNT_TIMEOUT_S,
    )
    found = re.findall(r"(\d+) tests? collected", out)
    if not found:
        return None
    return int(found[-1])


def run_build(frontend_dir: Path) -> tuple[int, str]:
    """``npm run build`` in the frontend dir (vite build, as CI runs it)."""
    return _lib.run(["npm", "run", "build"], frontend_dir, timeout=BUILD_TIMEOUT_S)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _emit(obj: dict) -> None:
    print(json.dumps(obj))


def _counter_path(root: Path, scope: str) -> Path:
    # Per scope so parallel SubagentStop gates can't reset the orchestrator's series.
    return _lib.state_dir(root) / f"consecutive_blocks.{scope}"


def _read_counter(root: Path, scope: str) -> int:
    try:
        return int(_counter_path(root, scope).read_text().strip() or 0)
    except (OSError, ValueError):
        return 0


def _write_counter(root: Path, scope: str, n: int) -> None:
    _counter_path(root, scope).write_text(str(n))


def _block(root: Path, fp: str, scope: str, check: str, detail: str) -> int:
    """Record a failure (fingerprint + consecutive counters) and emit the block."""
    _lib.bump_fail(root, fp)
    _write_counter(root, scope, _read_counter(root, scope) + 1)
    _emit({"decision": "block", "reason": f"{check}\n{_lib.tail(detail)}"})
    return 0


def _has_new_migration(root: Path, files: list[str]) -> bool:
    """A changed migration file that exists in the tree but not in HEAD."""
    for f in files:
        if MIGRATIONS_RE.match(f) and (root / f).exists():
            if _lib._git(root, "cat-file", "-e", f"HEAD:{f}") is None:
                return True
    return False


def _models_schema_changed(root: Path) -> bool:
    """True if the models.py diff adds/removes a schema-defining line."""
    raw = _lib._git(root, "diff", "HEAD", "--", MODELS_PATH)
    if not raw:
        return False
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")) and SCHEMA_LINE_RE.search(line):
            return True
    return False


def _compile_error(root: Path, backend: list[str]) -> str | None:
    """First syntax error among changed, existing backend ``.py`` files."""
    for f in backend:
        if not f.endswith(".py"):
            continue
        path = root / f
        if not path.is_file():
            continue
        try:
            src = path.read_bytes().decode("utf-8-sig")
            compile(src, f, "exec", dont_inherit=True)
        except SyntaxError as exc:
            return f"{f}:{exc.lineno}: {exc.msg}"
        except (ValueError, UnicodeDecodeError, OSError):
            continue  # not our job to judge unreadable files
    return None


def _deleted_test_module(root: Path) -> bool:
    """True if the diff deletes a ``backend/tests/**/test_*.py`` module (a
    removed feature legitimately takes its tests with it)."""
    for p in _lib.deleted_files(root):
        name = p.rsplit("/", 1)[-1]
        if p.startswith("backend/tests/") and name.startswith("test_") and name.endswith(".py"):
            return True
    return False


# --------------------------------------------------------------------------
# Gate
# --------------------------------------------------------------------------

def main(data: dict, scope: str = "stop") -> int:
    """Run the gate; always return 0 (the verdict is the JSON on stdout)."""
    try:
        return _gate(data, scope)
    except Exception:  # a gate bug must never wedge the session
        return 0


def _gate(data: dict, scope: str) -> int:
    root = _lib.repo_root(data.get("cwd"))
    if root is None:
        return 0

    # The orchestrator's turn can end while workers are still editing, so the tree
    # is mid-change. Each worker has its own SubagentStop gate and the next Stop
    # re-checks everything. (Field from the hook docs; absent => carry on.)
    if scope == "stop":
        tasks = data.get("background_tasks")
        if isinstance(tasks, list) and any(
            isinstance(t, dict) and t.get("type") == "subagent" for t in tasks
        ):
            return 0

    files = _lib.changed_files(root)
    backend = [f for f in files if f.startswith("backend/")]
    frontend = [f for f in files if f.startswith("frontend/")]
    if not backend and not frontend:
        return 0  # docs-only / hook-only changes never run anything

    fp = _lib.diff_fingerprint(root)
    if _lib.is_ok(root, fp) or (scope == "affected" and _lib.is_ok(root, fp + "-affected")):
        return 0

    # Loop guard. stop_hook_active alone does NOT stand down (see module docstring):
    # the per-tree fail counter stops a stuck tree, the consecutive cap stops an
    # endless series of *changing* failing trees.
    active = bool(data.get("stop_hook_active"))
    if not active:
        _write_counter(root, scope, 0)
    fails = _lib.fail_count(root, fp)
    consecutive = _read_counter(root, scope)
    if (fails >= 2
            or (active and fails >= 1)
            or (active and consecutive >= MAX_CONSECUTIVE_BLOCKS)):
        _emit({"systemMessage": STAND_DOWN_MSG})
        return 0

    # Migration check (both scopes).
    if MODELS_PATH in files and _models_schema_changed(root) and not _has_new_migration(root, files):
        return _block(
            root, fp, scope, "migration check failed",
            "models.py schema changed with no new Alembic migration (AGENTS.md §9)",
        )

    ran_all = True      # every applicable check actually ran (gates the .ok marks)
    n: int | None = None
    notes: list[str] = []
    backend_dir = root / "backend"

    if backend:
        err = _compile_error(root, backend)
        if err:
            return _block(root, fp, scope, "syntax check failed", err)

        py = _lib.venv_python()
        if py is None:
            ran_all = False
        else:
            tests = _lib.affected_tests(root, files)
            if tests is None:
                if scope == "stop":
                    code, out = run_pytest(py, None, backend_dir, STOP_PYTEST_TIMEOUT_S)
                    if code != 0:
                        return _block(root, fp, scope, "full test suite failed (core file changed)", out)
                else:
                    # T5: never the full suite in a subagent; Stop will run it.
                    ran_all = False
            elif tests:
                if scope == "stop":
                    # A subagent already proved this exact tree on its affected tests.
                    if not _lib.is_ok(root, fp + "-affected"):
                        code, out = run_pytest(py, tests, backend_dir, STOP_PYTEST_TIMEOUT_S)
                        if code != 0:
                            return _block(root, fp, scope, f"affected tests failed ({', '.join(tests)})", out)
                else:
                    code, out = run_pytest(py, tests, backend_dir, AFFECTED_PYTEST_TIMEOUT_S)
                    if code != 0:
                        return _block(root, fp, scope, f"affected tests failed ({', '.join(tests)})", out)
            # tests == []: nothing maps to these changes; counts as ran.

            if scope == "stop":
                n = count_tests(py, backend_dir)
                if n is not None:
                    baseline_file = _lib.state_dir(root) / (
                        "last_count." + re.sub(r"[^\w.-]", "_", _lib.current_branch(root))
                    )
                    try:
                        baseline = int(baseline_file.read_text().strip())
                    except (OSError, ValueError):
                        baseline = None
                    if baseline is not None and n < baseline and not _deleted_test_module(root):
                        return _block(
                            root, fp, scope, "test count guard failed",
                            f"suite count fell from {baseline} to {n} "
                            "(AGENTS.md §10: a session that lowers it isn't done)",
                        )

    if frontend and scope == "stop":
        if not (root / "frontend" / "node_modules").is_dir():
            ran_all = False
            notes.append("frontend build skipped: no node_modules in this tree")
        else:
            code, out = run_build(root / "frontend")
            if code != 0:
                return _block(root, fp, scope, "frontend build failed", out)

    # Everything that applies passed.
    _write_counter(root, scope, 0)
    if scope == "stop":
        if ran_all:
            _lib.mark_ok(root, fp)
        if n is not None:
            (_lib.state_dir(root) / (
                "last_count." + re.sub(r"[^\w.-]", "_", _lib.current_branch(root))
            )).write_text(str(n))
        _lib.prune_state(root)
    elif ran_all and backend:
        _lib.mark_ok(root, fp + "-affected")

    if notes:
        _emit({"systemMessage": "; ".join(notes)})
    return 0


if __name__ == "__main__":
    # Fail open even on a bad command line: an argparse error would exit 2,
    # which the hook protocol reads as a block.
    scope = "stop"
    try:
        parser = argparse.ArgumentParser(exit_on_error=False)
        parser.add_argument("--scope", choices=("stop", "affected"), default="stop")
        scope = parser.parse_known_args()[0].scope
    except (Exception, SystemExit):
        pass
    sys.exit(main(_lib.read_input(), scope))
