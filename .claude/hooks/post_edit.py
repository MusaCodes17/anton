"""PostToolUse fast checks for Anton's local verification hooks (phase R13).

Job: run in the foreground right after an Edit/Write/MultiEdit/NotebookEdit and
catch the cheap, deterministic mistakes before the next model turn:
- a backend ``.py`` that no longer compiles (syntax only: no import, no tests;
  post_edit_tests.py owns the background test run);
- hard-coded hex colours in new frontend component/page JSX (AGENTS.md §5:
  use Tailwind design tokens);
- a ``models.py`` change, a reminder that a schema change needs an Alembic
  migration (AGENTS.md §9).

Rationale / constraints:
- Synchronous, so it must stay fast: no subprocess, no pytest.
- Uses builtin ``compile()`` rather than ``py_compile``, because ``py_compile``
  writes ``__pycache__`` into the repo and a hook must not write there.
- Silent on success. PostToolUse cannot block the edit, so a failure exits 2
  (the only way stderr reaches Claude). The models.py reminder is the one
  deliberate non-silent success, for the same reason.
- Only the NEW text of an edit is scanned for hex colours: the repo already has
  some, and flagging old lines would block unrelated edits.
- An unexpected exception returns 0: a hook bug must never disturb the session.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Keep the hook from writing .pyc files for _lib into the repo.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib  # noqa: E402

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
MAX_HITS = 5
FRONTEND_PREFIXES = ("frontend/src/components/", "frontend/src/pages/")
MODELS_REL = "backend/app/models/models.py"


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


def _new_texts(tool_input: dict) -> list[str]:
    """The text an edit introduces: ``content`` (Write), ``new_string`` (Edit),
    or each ``edits[].new_string`` (MultiEdit)."""
    texts: list[str] = []
    if isinstance(tool_input.get("content"), str):
        texts.append(tool_input["content"])
    if isinstance(tool_input.get("new_string"), str):
        texts.append(tool_input["new_string"])
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
                texts.append(edit["new_string"])
    return texts


def _hex_hits(text: str) -> list[str]:
    """``"<hex>  |  <line>"`` for each hex literal outside comments and href values."""
    hits: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("//", "*", "{/*")):
            continue
        for m in HEX_RE.finditer(line):
            if line[: m.start()].endswith('href="'):
                continue
            hits.append(f"{m.group(0)}  |  {stripped[:120]}")
    return hits


def _check_backend(root: Path, rel: str) -> int:
    """Syntax-check a backend module; then the models.py schema reminder."""
    try:
        source = (root / rel).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return 0
    try:
        # dont_inherit: do not pick up this hook's `from __future__` flags.
        compile(source, rel, "exec", dont_inherit=True)
    except SyntaxError as exc:
        print(f"{rel}:{exc.lineno}: syntax error: {exc.msg}", file=sys.stderr)
        return 2
    if rel == MODELS_REL:
        print(
            "models.py changed: a schema change needs an Alembic migration (AGENTS.md §9).",
            file=sys.stderr,
        )
        return 2
    return 0


def _check_frontend(rel: str, tool_input: dict) -> int:
    """Flag hard-coded hex colours in the newly written text."""
    hits: list[str] = []
    for text in _new_texts(tool_input):
        hits.extend(_hex_hits(text))
    if not hits:
        return 0
    print(f"{rel}: hard-coded hex colour in new code:", file=sys.stderr)
    for hit in hits[:MAX_HITS]:
        print(f"  {hit}", file=sys.stderr)
    if len(hits) > MAX_HITS:
        print(f"  ... and {len(hits) - MAX_HITS} more", file=sys.stderr)
    print("use Tailwind design tokens, not hard-coded hex (AGENTS.md §5)", file=sys.stderr)
    return 2


def main(data: dict) -> int:
    """Return the hook exit code: 0 silent, 2 show stderr to Claude."""
    try:
        tool_input = data.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not isinstance(file_path, str) or not file_path:
            return 0
        root = _lib.repo_root(data.get("cwd"))
        if root is None:
            return 0
        rel = _repo_rel(file_path, root)
        if rel is None:
            return 0
        if rel.startswith("backend/") and rel.endswith(".py"):
            return _check_backend(root, rel)
        if rel.startswith(FRONTEND_PREFIXES) and rel.endswith(".jsx"):
            return _check_frontend(rel, tool_input)
        return 0
    except Exception:  # a hook bug must never disturb the session
        return 0


if __name__ == "__main__":
    sys.exit(main(_lib.read_input()))
