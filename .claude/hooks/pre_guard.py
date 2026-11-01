"""PreToolUse guard for Anton's local Claude Code hooks (phase R13, plan T3).

Job: stop an agent from touching the things that are expensive or impossible
to recover, and ask the human before the few actions that are sometimes right
but must be deliberate. It protects:
- secrets (``backend/.env`` and ``.env.*`` other than the tracked ``.env.example``),
- the live database and its backup copies (``*.db``, ``*.db.bak-*``) and anything
  under ``~/anton-data/``,
- applied migrations (an existing ``backend/alembic/versions/*.py`` that is already
  on ``origin/main`` is history: write a new migration instead),
- the pinned web stack (starlette / fastapi / sse-starlette / mcp are pinned
  together, AGENTS.md §6) and migration downgrades.

Rationale / constraints:
- Deny means the tool call is refused; ask means the human is prompted. Rules are
  checked deny-first, and the first match wins.
- Training history is sacred (AGENTS.md §2), so any write, delete, rm/mv or
  unrestricted ``sqlite3`` against ``shoe_deals.db`` asks. Reads via
  ``sqlite3 -readonly`` and plain ``cp`` of the file are allowed.
- Stdlib only, Python 3.10-compatible, and it fails open: any unexpected error
  prints nothing and exits 0, because a developer guard must never wedge a
  session.
- Silent on allow: ``main`` prints nothing for allowed calls.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lib  # noqa: E402

EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})
DB_NAME = "shoe_deals.db"
MIGRATIONS_REL = "backend/alembic/versions"

ENV_RE = re.compile(r"^\.env(\..+)?$")
DB_FILE_RE = re.compile(r"\.db($|[.-])")
WRITE_WORDS_RE = re.compile(r"\b(delete|update|insert|drop|alter|replace)\b", re.IGNORECASE)
RM_MV_RE = re.compile(r"\b(rm|mv)\b")
REDIRECT_RE = re.compile(r">\s*\S*shoe_deals\.db")
PIN_RE = re.compile(
    r"\bpip3?\b.*\binstall\b.*(?<![\w-])(starlette|fastapi|sse-starlette|mcp)\b"
)
DOWNGRADE_RE = re.compile(r"\balembic\b.*\bdowngrade\b")


def on_origin_main(root: Path, rel: str) -> bool:
    """True if ``rel`` exists in ``origin/main``. Kept module-level so tests can stub it.

    Any git failure (no remote ref, not a repo) reads as False, i.e. allow.
    """
    rc, _ = _lib.run(["git", "cat-file", "-e", f"origin/main:{rel}"], root, 15)
    return rc == 0


def _decide_edit(data: dict, ti: dict) -> tuple[str, str] | None:
    raw = ti.get("file_path")
    if not isinstance(raw, str) or not raw:
        return None
    path = os.path.expanduser(raw)
    p = Path(path)
    base = p.name

    if ENV_RE.match(base) and base != ".env.example" and p.parent.name == "backend":
        return (
            "deny",
            f"{base} under backend/ holds secrets and is not editable by the agent. "
            "Edit it by hand. (.env.example is the tracked template and is allowed.)",
        )
    if DB_FILE_RE.search(base):
        return (
            "deny",
            f"{base} is a database file or backup copy of live training and deal data. "
            "Do not write it directly; go through the services and sanctioned write paths.",
        )
    if "anton-data" in Path(os.path.normpath(path)).parts:
        return (
            "deny",
            "Paths under ~/anton-data/ are the live data directory. Do not write there "
            "from a tool call.",
        )

    root = _lib.repo_root(data.get("cwd"))
    if root is not None:
        try:
            rel = Path(os.path.abspath(path)).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = None
        if (
            rel is not None
            and Path(rel).parent.as_posix() == MIGRATIONS_REL
            and rel.endswith(".py")
            and on_origin_main(root, rel)
        ):
            return (
                "ask",
                f"{rel} is an applied migration already on origin/main. Applied migrations "
                "are history; write a new migration file instead of editing this one.",
            )
    return None


def _decide_bash(ti: dict) -> tuple[str, str] | None:
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not cmd:
        return None

    if DB_NAME in cmd:
        write_like = (
            ("sqlite3" in cmd and "-readonly" not in cmd)
            or WRITE_WORDS_RE.search(cmd)
            or RM_MV_RE.search(cmd)
            or REDIRECT_RE.search(cmd)
        )
        if write_like:
            return (
                "ask",
                "This command writes, deletes, moves or opens shoe_deals.db without -readonly. "
                "Training history is sacred (AGENTS.md §2). Reads should use sqlite3 -readonly. "
                "The allowlist has Bash(sqlite3 *), so this is the check that catches it.",
            )

    if PIN_RE.search(cmd):
        return (
            "ask",
            "starlette, fastapi, sse-starlette and mcp are pinned together to resolve the "
            "mcp[cli] conflict (AGENTS.md §6). Do not bump them independently.",
        )

    if DOWNGRADE_RE.search(cmd):
        return (
            "ask",
            "alembic downgrade reverses a schema migration on the live database. "
            "Confirm this is intended.",
        )
    return None


def decide(data: dict) -> tuple[str, str] | None:
    """Return ``("deny"|"ask", reason)`` for a risky tool call, or None to allow.

    Pure apart from the git lookup for migration edits. Deny rules are checked
    before ask rules, and the first match wins.
    """
    tool = data.get("tool_name")
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return None
    if tool in EDIT_TOOLS:
        return _decide_edit(data, ti)
    if tool == "Bash":
        return _decide_bash(ti)
    return None


def main(data: dict) -> int:
    """Print the hook decision JSON for a risky call; print nothing when allowed.

    Always returns 0. Any unexpected error is swallowed (fail open).
    """
    try:
        decision = decide(data)
        if decision is None:
            return 0
        kind, reason = decision
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": kind,
                "permissionDecisionReason": reason,
            }
        }))
    except Exception:  # fail open: a guard bug must never block the session
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(_lib.read_input()))
