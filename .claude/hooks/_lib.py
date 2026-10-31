"""Shared helpers for Anton's local Claude Code verification hooks (phase R13).

Job: give every hook script the same small, deterministic toolbox: read the
hook's stdin JSON, find the git tree to check, list what changed, map changed
backend files to the tests that cover them, fingerprint the tree so a proven-green
state is never re-tested, and exit with the hook protocol's codes.

Rationale / constraints:
- Stdlib only and Python 3.10-compatible, so a hook can run under any
  ``python3`` without the project venv (the venv is only needed to run pytest).
- Silent on success: ``ok()`` prints nothing; ``fail()`` prints only the tail of
  the message, so a failure costs Claude ~40 lines of context and a pass costs 0.
- Git/subprocess failures never raise out of the public helpers; they degrade to
  an empty answer (a hook that crashes would block work for the wrong reason).
- The checked tree comes from the hook input's ``cwd``, never from
  ``$CLAUDE_PROJECT_DIR``: inside a worktree the two differ, and the worktree is
  the tree being edited.
- All hook state lives in ``.claude/hooks/.state/`` (gitignored); nothing else
  is ever written.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Changing any of these can alter every test's behaviour, so the whole suite
# runs rather than a guessed subset. Anything under backend/alembic/ counts too.
CORE_FILES = frozenset(
    {
        "backend/app/models/models.py",
        "backend/app/database.py",
        "backend/tests/conftest.py",
        "backend/requirements.txt",
    }
)
CORE_PREFIXES = ("backend/alembic/",)

STATE_REL = ".claude/hooks/.state"


# --------------------------------------------------------------------------
# Input / environment
# --------------------------------------------------------------------------

def read_input() -> dict:
    """Parse the hook's stdin JSON; empty or invalid stdin yields ``{}``."""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _git(root: Path, *args: str) -> bytes | None:
    """Run git in ``root``; return stdout bytes, or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def repo_root(cwd: str | None) -> Path | None:
    """Top-level of the git tree containing ``cwd`` (fallback: process cwd).

    Deliberately not ``$CLAUDE_PROJECT_DIR``: in a worktree that points at the
    main checkout, but the tree under edit is the worktree.
    """
    start = cwd or os.getcwd()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout.strip()
    if proc.returncode != 0 or not out:
        return None
    return Path(out)


def venv_python() -> Path | None:
    """The project venv's python, or None.

    The venv exists only in the main checkout, and is run against the
    worktree's ``backend/``. Prefer ``$CLAUDE_PROJECT_DIR`` (main checkout even
    from a worktree), else the checkout this script lives in.
    """
    candidates = []
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    # .claude/hooks/_lib.py -> repo root is three levels up.
    candidates.append(Path(__file__).resolve().parents[2])
    for base in candidates:
        py = base / "backend" / "venv" / "bin" / "python"
        if py.exists():
            return py
    return None


# --------------------------------------------------------------------------
# Changed files
# --------------------------------------------------------------------------

def _status_entries(root: Path) -> list[tuple[str, list[str]]]:
    """Parse ``git status --porcelain=v1 -z`` into ``(XY, [paths])`` entries.

    Format: ``XY <path>\\0``; for rename/copy (R/C in either column) the entry
    is followed by one extra NUL-terminated field holding the *original* path.
    """
    raw = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if raw is None:
        return []
    fields = raw.decode("utf-8", "surrogateescape").split("\0")
    entries: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(fields):
        field = fields[i]
        i += 1
        if len(field) < 4:  # trailing empty field or malformed
            continue
        xy, path = field[:2], field[3:]
        paths = [path]
        if ("R" in xy or "C" in xy) and i < len(fields):
            paths.append(fields[i])  # old path
            i += 1
        if not any(p.startswith(STATE_REL + "/") for p in paths):
            entries.append((xy, paths))
    return entries


def changed_files(root: Path) -> list[str]:
    """Repo-relative paths differing from HEAD (tracked, staged, untracked,
    deleted; renames contribute both the new and old path). Sorted, unique."""
    return sorted({p for _, paths in _status_entries(root) for p in paths})


def deleted_files(root: Path) -> list[str]:
    """Paths deleted relative to HEAD (``D`` in either status column)."""
    return sorted({paths[0] for xy, paths in _status_entries(root) if "D" in xy})


# --------------------------------------------------------------------------
# Affected-test selection
# --------------------------------------------------------------------------

def is_core(path: str) -> bool:
    """True if a change to ``path`` should trigger the full test suite."""
    return path in CORE_FILES or path.startswith(CORE_PREFIXES)


def _imported_names(source: str, parent: str) -> set[str]:
    """Names pulled in by ``from <parent> import ...`` statements in ``source``.

    Handles aliases (``x as y``), comma lists, backslash continuations and
    parenthesised multi-line lists (with comments).
    """
    names: set[str] = set()
    pattern = re.compile(
        r"^[ \t]*from[ \t]+" + re.escape(parent) + r"[ \t]+import[ \t]+"
        r"(\((?P<paren>[^)]*)\)|(?P<plain>(?:[^\n\\]|\\\n)*))",
        re.MULTILINE,
    )
    for m in pattern.finditer(source):
        body = m.group("paren") if m.group("paren") is not None else m.group("plain")
        body = re.sub(r"#[^\n]*", "", body).replace("\\\n", " ")
        for part in body.split(","):
            tokens = part.split()
            if tokens:
                names.add(tokens[0])  # drop "as alias"
    return names


def affected_tests(root: Path, files: list[str]) -> list[str] | None:
    """Test modules (relative to ``backend/``, e.g. ``tests/test_x.py``) to run
    for ``files``; ``None`` means "run the full suite" (a core file changed)."""
    if any(is_core(f) for f in files):
        return None

    tests_dir = root / "backend" / "tests"
    selected: set[str] = set()
    app_modules: list[str] = []  # repo-relative backend/app/**.py

    for f in files:
        if f.startswith("backend/tests/") and f.endswith(".py"):
            name = f.rsplit("/", 1)[-1]
            if name.startswith("test_") and (root / f).exists():
                selected.add(f[len("backend/"):])
        elif f.startswith("backend/app/") and f.endswith(".py"):
            app_modules.append(f)

    if not app_modules or not tests_dir.is_dir():
        return sorted(selected)

    # Read every test file once. Labeled scale choice: ~90 small files at
    # personal scale, so a plain pass beats an index that could go stale.
    test_files = sorted(tests_dir.rglob("test_*.py"))
    sources: dict[Path, str] = {}
    for tf in test_files:
        try:
            sources[tf] = tf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    for f in app_modules:
        parts = f[len("backend/"):-len(".py")].split("/")  # app, services, x
        is_pkg = parts[-1] == "__init__"
        if is_pkg:
            parts = parts[:-1]
        if not parts:
            continue
        dotted = ".".join(parts)
        stem = parts[-1]
        parent = ".".join(parts[:-1])

        if not is_pkg:  # rule (1): test_<stem>*.py by name
            for tf in test_files:
                if tf.name.startswith(f"test_{stem}"):
                    selected.add(tf.relative_to(root / "backend").as_posix())

        dotted_re = re.compile(r"\b" + re.escape(dotted) + r"\b")
        for tf, src in sources.items():
            rel = tf.relative_to(root / "backend").as_posix()
            if rel in selected:
                continue
            if dotted_re.search(src) or (
                parent and stem in _imported_names(src, parent)
            ):
                selected.add(rel)

    return sorted(selected)


# --------------------------------------------------------------------------
# Fingerprint + state markers
# --------------------------------------------------------------------------

def diff_fingerprint(root: Path) -> str:
    """sha256 of the working-tree delta vs HEAD: ``git diff HEAD --binary`` plus
    each untracked file's path and contents (sorted). Excludes the hook state
    dir so writing markers never changes the fingerprint."""
    h = hashlib.sha256()
    h.update(_git(root, "diff", "HEAD", "--binary", "--", ".", f":(exclude){STATE_REL}") or b"")
    listing = _git(root, "ls-files", "--others", "--exclude-standard", "-z") or b""
    untracked = sorted(
        p for p in listing.decode("utf-8", "surrogateescape").split("\0")
        if p and not p.startswith(STATE_REL + "/")
    )
    for p in untracked:
        h.update(b"\0untracked\0" + p.encode("utf-8", "surrogateescape") + b"\0")
        try:
            h.update((root / p).read_bytes())
        except OSError:
            pass
    return h.hexdigest()


def state_dir(root: Path) -> Path:
    """``<root>/.claude/hooks/.state``, created if missing. The only place
    hooks write."""
    d = root / STATE_REL
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_ok(root: Path, fp: str) -> bool:
    """True if this exact tree already passed verification."""
    return (state_dir(root) / f"{fp}.ok").exists()


def mark_ok(root: Path, fp: str) -> None:
    """Record that this exact tree passed."""
    (state_dir(root) / f"{fp}.ok").touch()


def fail_count(root: Path, fp: str) -> int:
    """How many times this exact tree has failed (loop guard input)."""
    try:
        return int((state_dir(root) / f"{fp}.fail").read_text().strip() or 0)
    except (OSError, ValueError):
        return 0


def bump_fail(root: Path, fp: str) -> int:
    """Increment and return the failure counter for this tree."""
    n = fail_count(root, fp) + 1
    (state_dir(root) / f"{fp}.fail").write_text(str(n))
    return n


def prune_state(root: Path, keep: int = 50) -> None:
    """Delete the oldest ``.ok``/``.fail`` markers beyond ``keep``."""
    d = state_dir(root)
    markers = [p for p in d.iterdir() if p.suffix in (".ok", ".fail")]
    markers.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in markers[keep:]:
        try:
            p.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------
# Output / process helpers
# --------------------------------------------------------------------------

def tail(text: str, lines: int = 40) -> str:
    """Last ``lines`` lines of ``text`` (failures show only the end)."""
    return "\n".join(text.splitlines()[-lines:])


def ok() -> None:
    """Success: exit 0 with no output."""
    sys.exit(0)


def fail(msg: str) -> None:
    """Failure: print the tail of ``msg`` to stderr and exit 2 (hook block)."""
    print(tail(msg), file=sys.stderr)
    sys.exit(2)


def run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str]:
    """Run ``cmd``; return (returncode, combined stdout+stderr). A timeout
    yields (124, message), mirroring coreutils ``timeout``."""
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s: {' '.join(cmd)}"
    except OSError as exc:
        return 127, f"could not run {' '.join(cmd)}: {exc}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
