"""PostToolUse background test run for Anton's local verification hooks (phase R13).

Job: after an edit to a backend ``.py``, run only the test modules that cover it
(``_lib.affected_tests``). Wired with ``asyncRewake``: a pass is silent and costs
nothing; a failure exits 2, which wakes Claude with the tail of the pytest output.

Rationale / constraints:
- Affected modules only. A core file, or a file with no mapped tests, returns 0:
  the Stop gate runs the full suite, so this hook never duplicates it.
- Debounce: a burst of edits (source, then its test) would otherwise report the
  half-done state. The fingerprint is taken, the hook waits DEBOUNCE_S, and it
  continues only if the tree did not move. The last edit's hook does the check.
- One run at a time via a non-blocking flock. A skipped run is covered by Stop.
- A failure whose tree has since changed is stale and is dropped silently.
- A pass does NOT mark the tree ok: this is a subset run, and only Stop may
  record a full pass.
- Runs the project venv's pytest against the worktree's backend/, as CI does.
- Duplicates the small ``_repo_rel`` helper from post_edit.py on purpose, so the
  two hooks stay independent scripts.
"""
from __future__ import annotations

import fcntl
import sys
import time
from pathlib import Path

# Keep the hook from writing .pyc files for _lib into the repo.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib  # noqa: E402

# Settle window for a burst of edits. Long enough for a follow-up edit (the test
# after the source) to land, short enough that a lone edit still reports promptly.
DEBOUNCE_S = 5
TEST_TIMEOUT_S = 300
LOCK_NAME = "post_edit.lock"


def _repo_rel(file_path: str, root: Path) -> str | None:
    """Repo-relative posix path of ``file_path`` (relative paths resolve against
    ``root``), or None if it lies outside the repo."""
    p = Path(file_path)
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def run_tests(py: Path, tests: list[str], backend_dir: Path) -> tuple[int, str]:
    """Run the given test modules with the venv python. Separate function so
    tests can stub it."""
    return _lib.run(
        [str(py), "-m", "pytest", "-q", "--tb=short", "--disable-warnings", *tests],
        backend_dir,
        timeout=TEST_TIMEOUT_S,
    )


def main(data: dict) -> int:
    """Return the hook exit code: 0 silent, 2 wakes Claude with the failure tail."""
    try:
        tool_input = data.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        file_path = tool_input.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            return 0
        root = _lib.repo_root(data.get("cwd"))
        if root is None:
            return 0
        rel = _repo_rel(file_path, root)
        if rel is None or not (rel.startswith("backend/") and rel.endswith(".py")):
            return 0

        # None = core file (Stop runs everything); [] = no mapped tests.
        tests = _lib.affected_tests(root, [rel])
        if not tests:
            return 0
        py = _lib.venv_python()
        if py is None:
            return 0

        # Debounce: continue only if the tree was still for DEBOUNCE_S.
        before = _lib.diff_fingerprint(root)
        time.sleep(DEBOUNCE_S)
        fp = _lib.diff_fingerprint(root)
        if fp != before:
            return 0
        if _lib.is_ok(root, fp):
            return 0

        lock_fh = open(_lib.state_dir(root) / LOCK_NAME, "w")
        try:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return 0  # another run holds the lock; Stop catches anything skipped
            code, out = run_tests(py, tests, root / "backend")
        finally:
            lock_fh.close()

        if code == 0:
            return 0
        if _lib.diff_fingerprint(root) != fp:
            return 0  # the tree moved on, so this failure is stale
        print(f"affected tests failed ({', '.join(tests)}):", file=sys.stderr)
        print(_lib.tail(out), file=sys.stderr)
        return 2
    except Exception:  # a hook bug must never disturb the session
        return 0


if __name__ == "__main__":
    sys.exit(main(_lib.read_input()))
