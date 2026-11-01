"""Tests for the local Claude Code verification hooks (`.claude/hooks/`, phase R13).

The hooks guard every agent session, and a silent regression (a guard that no
longer denies, a gate that stops blocking) would go unnoticed, so CI pins them.

Rules under test:
- pre_guard: secrets, database files, ~/anton-data and applied migrations are
  denied/asked; the sanctioned neighbours (.env.example, sqlite3 -readonly,
  non-pinned pip packages) are allowed; output is exactly the documented
  ``hookSpecificOutput`` shape and garbage input fails open.
- _lib: affected-test selection (including parenthesised multi-line imports),
  changed-file listing, and a fingerprint that ignores the hook's own state.
- post_edit / post_edit_tests: syntax and hex-colour checks, the models.py
  migration reminder, and the stale-failure drop for the background test run.
- stop_gate: the state machine. Failures block; the loop guard has three limbs
  (per-tree counter, ``stop_hook_active`` + a prior failure, consecutive cap) and
  ``stop_hook_active`` alone must NOT stand down, or every fix would go
  unverified. Count guard, migration check, scopes, fail-open.

Every test runs in a throwaway git repo (copied from one template). pytest,
test counting, the vite build and ``git cat-file origin/main`` are stubbed, so
nothing slow or environment-bound (venv, node_modules, .env) is needed.
"""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The scripts put their own dir on sys.path to find `_lib`, so no setup needed.
pre_guard = _load("claude_hook_pre_guard", "pre_guard.py")
post_edit = _load("claude_hook_post_edit", "post_edit.py")
post_edit_tests = _load("claude_hook_post_edit_tests", "post_edit_tests.py")
stop_gate = _load("claude_hook_stop_gate", "stop_gate.py")
_lib = stop_gate._lib  # the module object the scripts actually use

FOO = "backend/app/services/foo.py"
MODELS = "backend/app/models/models.py"
MIGRATION_OLD = "backend/alembic/versions/0001_init.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _template_repo(tmp_path_factory):
    """One committed repo, built once and copied per test (git init is slow)."""
    repo = tmp_path_factory.mktemp("hooks_template") / "repo"
    files = {
        FOO: "VALUE = 1\n",
        "backend/tests/test_foo.py": "def test_foo():\n    assert True\n",
        MODELS: '"""Models."""\nfrom sqlalchemy import Column, Integer\n\n\n'
                'class Foo:\n    __tablename__ = "foos"\n    id = Column(Integer)\n',
        MIGRATION_OLD: "revision = '0001'\n",
    }
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Hook Test")
    _git(repo, "config", "user.email", "hooks@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.fixture
def repo(_template_repo, tmp_path):
    dest = tmp_path / "repo"
    shutil.copytree(_template_repo, dest)
    return dest


@pytest.fixture(autouse=True)
def _hook_env(monkeypatch):
    """No venv, no debounce, no origin/main lookup, no reliance on CLAUDE_PROJECT_DIR."""
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setattr(_lib, "venv_python", lambda: Path("/fake/venv/bin/python"))
    monkeypatch.setattr(post_edit_tests, "DEBOUNCE_S", 0)
    monkeypatch.setattr(pre_guard, "on_origin_main", lambda root, rel: False)


class Gate:
    """Drives ``stop_gate.main`` with the slow steps stubbed and recorded."""

    def __init__(self, repo: Path, capsys, monkeypatch):
        self.repo, self.capsys = repo, capsys
        self.pytest_calls: list = []
        self.count_calls = 0
        self.build_calls = 0
        self.pytest_rc: tuple = (0, "ok")
        self.count: int | None = 10
        self.build_rc: tuple = (0, "")
        self._n = 0
        monkeypatch.setattr(stop_gate, "run_pytest", self._pytest)
        monkeypatch.setattr(stop_gate, "count_tests", self._count)
        monkeypatch.setattr(stop_gate, "run_build", self._build)

    def _pytest(self, py, tests, backend_dir, timeout):
        self.pytest_calls.append(tests)
        return self.pytest_rc

    def _count(self, py, backend_dir):
        self.count_calls += 1
        return self.count

    def _build(self, frontend_dir):
        self.build_calls += 1
        return self.build_rc

    def edit(self, rel: str = FOO) -> None:
        """Change a file to content never seen before (a new tree fingerprint)."""
        self._n += 1
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"VALUE = {self._n + 100}\n")  # never the committed content

    def write(self, rel: str, text: str) -> None:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def run(self, scope: str = "stop", **data):
        self.capsys.readouterr()
        assert stop_gate.main({"cwd": str(self.repo), **data}, scope) == 0
        out = self.capsys.readouterr().out.strip()
        return json.loads(out) if out else None

    def fp(self) -> str:
        return _lib.diff_fingerprint(self.repo)

    def set_baseline(self, n: int, branch: str | None = None) -> None:
        name = branch or _lib.current_branch(self.repo)
        (_lib.state_dir(self.repo) / f"last_count.{name}").write_text(str(n))


@pytest.fixture
def gate(repo, capsys, monkeypatch):
    return Gate(repo, capsys, monkeypatch)


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _edit(path, **extra) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": str(path)}, **extra}


# --------------------------------------------------------------------------
# pre_guard
# --------------------------------------------------------------------------

def test_guard_denies_backend_env_but_allows_env_example(tmp_path):
    assert pre_guard.decide(_edit(tmp_path / "backend" / ".env"))[0] == "deny"
    assert pre_guard.decide(_edit(tmp_path / "backend" / ".env.production"))[0] == "deny"
    assert pre_guard.decide(_edit(tmp_path / "backend" / ".env.example")) is None


@pytest.mark.parametrize("name", ["shoe_deals.db", "shoe_deals.db.bak-canonical"])
def test_guard_denies_db_files_and_backups(tmp_path, name):
    assert pre_guard.decide(_edit(tmp_path / name))[0] == "deny"


def test_guard_denies_anton_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert pre_guard.decide(_edit("~/anton-data/x"))[0] == "deny"


@pytest.mark.parametrize("cmd, expected", [
    ('sqlite3 ~/anton-data/shoe_deals.db "DELETE FROM activities"', "ask"),
    ('sqlite3 -readonly ~/anton-data/shoe_deals.db "SELECT 1"', None),
    ("rm ~/anton-data/shoe_deals.db", "ask"),
    ("venv/bin/python -m pytest -q", None),
    ("pip install fastapi", "ask"),
    ("pip install requests", None),
    ("pip install fastmcp-x", None),  # substring "mcp" is not the pinned package
    ("alembic downgrade -1", "ask"),
])
def test_guard_bash_rules(cmd, expected):
    decision = pre_guard.decide(_bash(cmd))
    assert (decision[0] if decision else None) == expected


@pytest.mark.parametrize("on_main, expected", [(True, "ask"), (False, None)])
def test_guard_migration_edit_asks_only_when_on_origin_main(repo, monkeypatch, on_main, expected):
    monkeypatch.setattr(pre_guard, "on_origin_main", lambda root, rel: on_main)
    decision = pre_guard.decide(_edit(repo / MIGRATION_OLD, cwd=str(repo)))
    assert (decision[0] if decision else None) == expected


def test_guard_deny_output_is_exactly_the_documented_shape(capsys, tmp_path):
    assert pre_guard.main(_edit(tmp_path / "backend" / ".env")) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"hookSpecificOutput"}
    hso = out["hookSpecificOutput"]
    assert set(hso) == {"hookEventName", "permissionDecision", "permissionDecisionReason"}
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert hso["permissionDecisionReason"]


def test_guard_allowed_call_prints_nothing(capsys):
    assert pre_guard.main(_bash("venv/bin/python -m pytest -q")) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("garbage", ["garbage", None, [], {"tool_name": 5, "tool_input": "x"}])
def test_guard_garbage_input_fails_open(capsys, garbage):
    assert pre_guard.main(garbage) == 0
    assert capsys.readouterr().out == ""


def test_read_input_tolerates_invalid_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert _lib.read_input() == {}
    monkeypatch.setattr("sys.stdin", io.StringIO("[1, 2]"))
    assert _lib.read_input() == {}


# --------------------------------------------------------------------------
# _lib: affected_tests / changed_files / diff_fingerprint
# --------------------------------------------------------------------------

def test_affected_tests_maps_name_and_parenthesised_multiline_importer(repo):
    (repo / "backend/tests/test_bar.py").write_text(
        "from app.services import (\n    foo as f,  # alias\n)\n\n\ndef test_bar():\n    pass\n"
    )
    (repo / "backend/tests/test_unrelated.py").write_text("from app.services import other\n")
    assert _lib.affected_tests(repo, [FOO]) == ["tests/test_bar.py", "tests/test_foo.py"]


def test_affected_tests_core_files_mean_full_suite(repo):
    assert _lib.affected_tests(repo, [MODELS]) is None
    assert _lib.affected_tests(repo, ["backend/alembic/x.py"]) is None


def test_affected_tests_docs_select_nothing_and_deleted_test_is_skipped(repo):
    assert _lib.affected_tests(repo, ["docs/changelog.md"]) == []
    (repo / "backend/tests/test_foo.py").unlink()
    assert _lib.affected_tests(repo, ["backend/tests/test_foo.py"]) == []


def test_changed_files_covers_staged_untracked_deleted_and_spaces(repo):
    (repo / "staged.py").write_text("x = 1\n")
    _git(repo, "add", "staged.py")
    (repo / "backend/new.py").write_text("y = 1\n")
    (repo / "backend/app/my file.py").write_text("z = 1\n")
    (repo / "backend/tests/test_foo.py").unlink()
    changed = _lib.changed_files(repo)
    assert {"staged.py", "backend/new.py", "backend/app/my file.py",
            "backend/tests/test_foo.py"} <= set(changed)
    assert _lib.deleted_files(repo) == ["backend/tests/test_foo.py"]


def test_fingerprint_is_stable_changes_with_content_and_ignores_state(repo):
    base = _lib.diff_fingerprint(repo)
    assert _lib.diff_fingerprint(repo) == base
    (repo / FOO).write_text("VALUE = 2\n")
    edited = _lib.diff_fingerprint(repo)
    assert edited != base
    (repo / FOO).write_text("VALUE = 3\n")
    assert _lib.diff_fingerprint(repo) != edited
    _lib.mark_ok(repo, edited)
    _lib.bump_fail(repo, edited)
    assert _lib.diff_fingerprint(repo) == _lib.diff_fingerprint(repo)
    (repo / FOO).write_text("VALUE = 2\n")
    assert _lib.diff_fingerprint(repo) == edited  # markers written, still equal


# --------------------------------------------------------------------------
# post_edit
# --------------------------------------------------------------------------

def _post(repo, rel, capsys, **tool_input) -> tuple[int, str]:
    capsys.readouterr()
    rc = post_edit.main({"cwd": str(repo), "tool_input": {"file_path": str(repo / rel), **tool_input}})
    return rc, capsys.readouterr().err


def test_post_edit_valid_python_is_silent_and_leaves_no_pycache(repo, capsys):
    rc, err = _post(repo, FOO, capsys)
    assert (rc, err) == (0, "")
    assert not list((repo / "backend").rglob("__pycache__"))


def test_post_edit_broken_python_reports_file_and_line(repo, capsys):
    (repo / FOO).write_text("VALUE = 1\ndef broken(:\n")
    rc, err = _post(repo, FOO, capsys)
    assert rc == 2
    assert f"{FOO}:2" in err
    assert not list((repo / "backend").rglob("__pycache__"))


JSX = "frontend/src/components/Btn.jsx"


def test_post_edit_hex_in_new_string_is_rejected(repo, capsys):
    rc, err = _post(repo, JSX, capsys, new_string="const s = { color: '#ff0000' }")
    assert rc == 2 and "#ff0000" in err


def test_post_edit_hex_in_comment_is_allowed(repo, capsys):
    assert _post(repo, JSX, capsys, new_string="// brand was #ff0000\nconst a = 1")[0] == 0


def test_post_edit_existing_hex_outside_new_text_is_ignored(repo, capsys):
    (repo / JSX).parent.mkdir(parents=True)
    (repo / JSX).write_text("const old = '#ff0000'\n")
    assert _post(repo, JSX, capsys, new_string="const fresh = 1")[0] == 0


def test_post_edit_models_py_gets_migration_reminder(repo, capsys):
    rc, err = _post(repo, MODELS, capsys)
    assert rc == 2 and "migration" in err.lower()


# --------------------------------------------------------------------------
# post_edit_tests
# --------------------------------------------------------------------------

def _post_tests(repo, rel, capsys) -> tuple[int, str]:
    capsys.readouterr()
    rc = post_edit_tests.main({"cwd": str(repo), "tool_input": {"file_path": str(repo / rel)}})
    return rc, capsys.readouterr().err


def test_post_tests_failure_on_still_tree_wakes_claude_with_tail(repo, capsys, monkeypatch):
    out = "\n".join(f"line {i}" for i in range(100)) + "\nFAILED tests/test_foo.py"
    monkeypatch.setattr(post_edit_tests, "run_tests", lambda py, tests, bd: (1, out))
    (repo / FOO).write_text("VALUE = 2\n")
    rc, err = _post_tests(repo, FOO, capsys)
    assert rc == 2
    assert "tests/test_foo.py" in err and "FAILED tests/test_foo.py" in err
    assert "line 0\n" not in err  # only the tail


def test_post_tests_stale_failure_is_dropped_when_tree_moves(repo, capsys, monkeypatch):
    def mutate_then_fail(py, tests, bd):
        (repo / FOO).write_text("VALUE = 99\n")
        return 1, "FAILED"
    monkeypatch.setattr(post_edit_tests, "run_tests", mutate_then_fail)
    (repo / FOO).write_text("VALUE = 2\n")
    assert _post_tests(repo, FOO, capsys) == (0, "")


def test_post_tests_core_file_does_not_run_anything(repo, capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(post_edit_tests, "run_tests", lambda *a: calls.append(a) or (1, "x"))
    assert _post_tests(repo, MODELS, capsys) == (0, "")
    assert calls == []


# --------------------------------------------------------------------------
# stop_gate: skip paths
# --------------------------------------------------------------------------

def test_gate_unchanged_tree_runs_nothing(gate):
    assert gate.run() is None
    assert gate.pytest_calls == [] and gate.count_calls == 0


def test_gate_tree_with_ok_marker_is_not_retested(gate):
    gate.edit()
    _lib.mark_ok(gate.repo, gate.fp())
    assert gate.run() is None
    assert gate.pytest_calls == []


def test_gate_docs_only_change_runs_nothing(gate):
    gate.write("docs/changelog.md", "# notes\n")
    assert gate.run() is None
    assert gate.pytest_calls == [] and gate.count_calls == 0


# --------------------------------------------------------------------------
# stop_gate: failure + loop guard
# --------------------------------------------------------------------------

def test_gate_failure_blocks_and_bumps_fail_counter(gate):
    gate.edit()
    gate.pytest_rc = (1, "FAILED tests/test_foo.py::test_foo")
    out = gate.run()
    assert out["decision"] == "block"
    assert "FAILED tests/test_foo.py::test_foo" in out["reason"]
    assert _lib.fail_count(gate.repo, gate.fp()) == 1
    assert not _lib.is_ok(gate.repo, gate.fp())


def test_loop_guard_same_tree_with_stop_hook_active_after_one_failure_stands_down(gate):
    gate.edit()
    gate.pytest_rc = (1, "FAILED")
    assert gate.run()["decision"] == "block"
    out = gate.run(stop_hook_active=True)
    assert out == {"systemMessage": stop_gate.STAND_DOWN_MSG}
    assert len(gate.pytest_calls) == 1  # no second pytest run


def test_loop_guard_same_tree_stands_down_after_two_failures_even_if_inactive(gate):
    gate.edit()
    gate.pytest_rc = (1, "FAILED")
    assert gate.run()["decision"] == "block"
    assert gate.run()["decision"] == "block"  # one failure alone does not stand down
    assert gate.run() == {"systemMessage": stop_gate.STAND_DOWN_MSG}
    assert len(gate.pytest_calls) == 2


def test_stop_hook_active_alone_does_not_stand_down_so_a_fix_is_still_verified(gate):
    """The reason the flag by itself is not a stand-down: the tree after a
    block is Claude's fix, and it must be tested, not waved through."""
    gate.edit()
    gate.pytest_rc = (1, "FAILED")
    assert gate.run()["decision"] == "block"
    gate.edit()  # the fix: a new tree with no recorded failure
    gate.pytest_rc = (0, "ok")
    assert gate.run(stop_hook_active=True) is None
    assert len(gate.pytest_calls) == 2  # pytest really re-ran
    assert _lib.is_ok(gate.repo, gate.fp())


def test_loop_guard_consecutive_cap_boundary_with_changing_trees(gate):
    gate.pytest_rc = (1, "FAILED")
    for i in range(stop_gate.MAX_CONSECUTIVE_BLOCKS):  # the last of these is the boundary
        gate.edit()
        out = gate.run(stop_hook_active=i > 0)
        assert out["decision"] == "block", f"block {i + 1} should still block"
    gate.edit()
    assert gate.run(stop_hook_active=True) == {"systemMessage": stop_gate.STAND_DOWN_MSG}
    assert len(gate.pytest_calls) == stop_gate.MAX_CONSECUTIVE_BLOCKS


# --------------------------------------------------------------------------
# stop_gate: count guard
# --------------------------------------------------------------------------

def test_count_guard_blocks_a_drop_and_names_both_numbers(gate):
    gate.edit()
    gate.set_baseline(10)
    gate.count = 9
    out = gate.run()
    assert out["decision"] == "block"
    assert "10" in out["reason"] and "9" in out["reason"]


def test_count_guard_allows_a_drop_when_a_test_module_is_deleted(gate):
    (gate.repo / "backend/tests/test_foo.py").unlink()
    gate.set_baseline(10)
    gate.count = 9
    assert gate.run() is None
    assert _lib.is_ok(gate.repo, gate.fp())


def test_count_guard_ignores_another_branchs_baseline(gate):
    gate.edit()
    gate.set_baseline(99, branch="some-other-branch")
    gate.count = 5
    assert gate.run() is None


def test_count_guard_is_skipped_when_count_is_unknown(gate):
    gate.edit()
    gate.set_baseline(99)
    gate.count = None
    assert gate.run() is None


def test_count_guard_pass_records_baseline_for_this_branch(gate):
    gate.edit()
    gate.count = 7
    assert gate.run() is None
    baseline = _lib.state_dir(gate.repo) / f"last_count.{_lib.current_branch(gate.repo)}"
    assert baseline.read_text() == "7"


# --------------------------------------------------------------------------
# stop_gate: migration check
# --------------------------------------------------------------------------

COLUMN = '"""Models."""\nfrom sqlalchemy import Column, Integer\n\n\nclass Foo:\n' \
         '    __tablename__ = "foos"\n    id = Column(Integer)\n    name = Column(Integer)\n'


def test_migration_check_blocks_schema_line_without_new_migration(gate):
    gate.write(MODELS, COLUMN)
    out = gate.run()
    assert out["decision"] == "block" and "migration" in out["reason"]
    assert gate.pytest_calls == []


def test_migration_check_passes_with_a_new_migration_file(gate):
    gate.write(MODELS, COLUMN)
    gate.write("backend/alembic/versions/0002_add_name.py", "revision = '0002'\n")
    assert gate.run() is None


def test_migration_check_passes_for_docstring_only_models_edit(gate):
    gate.write(MODELS, COLUMN.replace('"""Models."""', '"""Models, documented."""').replace(
        "    name = Column(Integer)\n", ""))
    assert gate.run() is None


def test_migration_already_in_head_does_not_count_as_new(gate):
    gate.write(MODELS, COLUMN)
    gate.write(MIGRATION_OLD, "revision = '0001'  # touched\n")
    assert gate.run()["decision"] == "block"


# --------------------------------------------------------------------------
# stop_gate: background tasks, compile, fail-open
# --------------------------------------------------------------------------

def test_background_subagent_makes_stop_silent_even_on_a_broken_tree(gate):
    gate.write(FOO, "def broken(:\n")
    assert gate.run(background_tasks=[{"type": "subagent"}]) is None
    assert gate.pytest_calls == []


def test_background_shell_task_does_not_skip_the_gate(gate):
    gate.edit()
    assert gate.run(background_tasks=[{"type": "shell"}]) is None
    assert gate.pytest_calls == [["tests/test_foo.py"]]


def test_syntax_error_in_changed_backend_file_blocks_before_pytest(gate):
    gate.write(FOO, "def broken(:\n")
    out = gate.run()
    assert out["decision"] == "block" and f"{FOO}:1" in out["reason"]
    assert gate.pytest_calls == []


def test_gate_fails_open_on_unexpected_exception(gate, monkeypatch):
    def boom(root):
        raise RuntimeError("git exploded")
    monkeypatch.setattr(stop_gate._lib, "changed_files", boom)
    assert gate.run() is None


# --------------------------------------------------------------------------
# stop_gate: affected scope (SubagentStop)
# --------------------------------------------------------------------------

def test_affected_scope_core_file_never_runs_full_suite_or_marks_affected(gate):
    gate.write(MODELS, COLUMN.replace('"""Models."""', '"""Models, documented."""').replace(
        "    name = Column(Integer)\n", ""))
    assert gate.run(scope="affected") is None
    assert gate.pytest_calls == []  # never pytest(tests=None)
    assert not _lib.is_ok(gate.repo, gate.fp() + "-affected")


def test_affected_scope_pass_marks_affected_and_stop_then_skips_pytest(gate):
    gate.edit()
    assert gate.run(scope="affected") is None
    assert gate.pytest_calls == [["tests/test_foo.py"]]
    assert _lib.is_ok(gate.repo, gate.fp() + "-affected")
    assert not _lib.is_ok(gate.repo, gate.fp())  # only Stop records a full pass
    assert gate.run() is None  # Stop on the same tree
    assert gate.pytest_calls == [["tests/test_foo.py"]]  # not re-run
    assert gate.count_calls == 1  # count guard still runs
    assert _lib.is_ok(gate.repo, gate.fp())


def test_affected_scope_skips_count_guard_and_frontend_build(gate):
    gate.edit()
    gate.write("frontend/src/App.jsx", "export default null\n")
    (gate.repo / "frontend" / "node_modules").mkdir()
    assert gate.run(scope="affected") is None
    assert gate.count_calls == 0 and gate.build_calls == 0


# --------------------------------------------------------------------------
# stop_gate: frontend
# --------------------------------------------------------------------------

def test_frontend_change_without_node_modules_notes_skip_and_no_ok_marker(gate):
    gate.write("frontend/src/App.jsx", "export default null\n")
    out = gate.run()
    assert "frontend build skipped" in out["systemMessage"]
    assert gate.build_calls == 0
    assert not _lib.is_ok(gate.repo, gate.fp())


def test_frontend_build_failure_blocks_when_node_modules_exists(gate):
    gate.write("frontend/src/App.jsx", "export default null\n")
    (gate.repo / "frontend" / "node_modules").mkdir()
    gate.build_rc = (1, "vite: build failed")
    out = gate.run()
    assert out["decision"] == "block" and "vite: build failed" in out["reason"]


# --- settings.json wiring ---

SETTINGS_PATH = HOOKS_DIR.parent / "settings.json"
EXPECTED_HOOK_SCRIPTS = {"pre_guard.py", "post_edit.py", "post_edit_tests.py", "stop_gate.py"}


def _settings_hook_entries() -> list[tuple[str, dict]]:
    """Return (event, hook) pairs for every command hook in settings.json."""
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    pairs = []
    for event, groups in settings["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                pairs.append((event, hook))
    return pairs


def _script_name(command: str) -> str:
    """Extract the ``<name>.py`` script from a ``.claude/hooks/`` command line."""
    marker = ".claude/hooks/"
    start = command.index(marker) + len(marker)
    end = command.index(".py", start) + len(".py")
    return command[start:end]


def test_settings_wire_every_hook_script():
    scripts = set()
    for _event, hook in _settings_hook_entries():
        name = _script_name(hook["command"])
        assert (HOOKS_DIR / name).is_file(), f"settings.json references missing hook {name}"
        scripts.add(name)
    assert scripts == EXPECTED_HOOK_SCRIPTS


def test_settings_subagent_gate_is_affected_scope_and_tests_run_async():
    by_event: dict[str, list[dict]] = {}
    for event, hook in _settings_hook_entries():
        by_event.setdefault(event, []).append(hook)

    subagent = by_event["SubagentStop"]
    assert len(subagent) == 1
    assert "--scope affected" in subagent[0]["command"]

    stop = by_event["Stop"]
    assert len(stop) == 1
    assert "--scope" not in stop[0]["command"]

    post = {_script_name(h["command"]): h for h in by_event["PostToolUse"]}
    assert post["post_edit_tests.py"].get("asyncRewake") is True
    assert not post["post_edit.py"].get("asyncRewake")


def test_test_running_pytest_commands_disable_warnings(repo, monkeypatch):
    """The hooks show Claude only the tail of pytest output, and the Pydantic
    deprecation warnings summary would push the real failure out of it. Every
    command that runs tests must pass --disable-warnings (the --collect-only
    count call is exempt: its output is not shown as a failure tail)."""
    calls = []
    monkeypatch.setattr(_lib, "run", lambda cmd, cwd, timeout=None: calls.append(cmd) or (0, ""))
    py = Path("/fake/venv/bin/python")
    post_edit_tests.run_tests(py, ["tests/test_foo.py"], repo / "backend")
    stop_gate.run_pytest(py, None, repo / "backend", 1)
    stop_gate.run_pytest(py, ["tests/test_foo.py"], repo / "backend", 1)
    assert len(calls) == 3
    for cmd in calls:
        assert "--disable-warnings" in cmd, cmd
