"""
Son of Anton's self-connection to Anton's MCP server (debt P2).

The assistant used to reach its own /mcp over loopback HTTP with a bearer token;
drop the token or change the port and it silently lost all tools. The default
transport is now an in-process, in-memory MCP session against the same FastMCP
instance. Rules under test:
  - memory transport needs no ANTON_SECRET and no listening port, and exposes the
    real Anton tools;
  - a confirmed proposal's executor (call_tool_once) runs the same tool, on the
    same DB, over that session;
  - ANTON_MCP_TRANSPORT=http still builds the bearer-carrying HTTP params;
  - a failing in-process connect is logged and skipped, never raised;
  - the session (and its server task) is torn down when the block exits.

Plain `asyncio.run` in sync tests, as elsewhere in the suite (no pytest-asyncio).
"""
import asyncio
import json
import logging
from contextlib import contextmanager

import pytest

from app import mcp_server
from app.services import chat_service
from app.services.chat_service import _connected_group, call_tool_once


@pytest.fixture(autouse=True)
def _memory_transport(monkeypatch):
    """Default transport, with no secret and no URL override leaking in from the env."""
    monkeypatch.delenv("ANTON_SECRET", raising=False)
    monkeypatch.delenv("ANTON_MCP_TRANSPORT", raising=False)
    monkeypatch.setattr(chat_service, "ANTON_MCP_TRANSPORT", "memory")


@pytest.fixture()
def test_db_session(db, monkeypatch):
    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)
    return db


def test_memory_transport_connects_without_secret_or_port(monkeypatch):
    # Nothing listens on 8000 in the test run; point the URL somewhere dead anyway
    # so a stray HTTP attempt could not pass by accident.
    monkeypatch.setitem(chat_service.MCP_SERVERS[0], "url", "http://127.0.0.1:1/mcp")

    async def go():
        async with _connected_group(sse_read_timeout_s=30) as group:
            return set(group.tools), len(group.sessions)

    names, n_sessions = asyncio.run(go())
    assert n_sessions == 1
    assert {"get_owned_shoes", "get_shoe_insights", "get_training_trends"} <= names


def test_call_tool_once_runs_the_real_tool_in_memory(test_db_session):
    text, ok = asyncio.run(call_tool_once("get_planned_races", {}))
    assert ok is True, text
    assert json.loads(text) == {"races": []}


def test_call_tool_once_unknown_tool_is_a_clean_failure():
    text, ok = asyncio.run(call_tool_once("no_such_tool", {}))
    assert ok is False
    assert "not available" in json.loads(text)["error"]


def test_http_transport_still_sends_bearer(monkeypatch):
    monkeypatch.setenv("ANTON_MCP_TRANSPORT", "http")
    monkeypatch.setenv("ANTON_SECRET", "s3cret-for-test")
    monkeypatch.setitem(chat_service.MCP_SERVERS[0], "url", "http://example.invalid/mcp")
    captured = []

    async def fake_connect(self, params, *a, **kw):
        captured.append(params)

    monkeypatch.setattr(chat_service.ClientSessionGroup, "connect_to_server", fake_connect)

    async def go():
        async with _connected_group(sse_read_timeout_s=42) as group:
            return len(group.sessions)

    assert asyncio.run(go()) == 0  # nothing really connected; no network touched
    assert len(captured) == 1
    params = captured[0]
    assert isinstance(params, chat_service.StreamableHttpParameters)
    assert params.url == "http://example.invalid/mcp"
    assert params.headers["Authorization"].startswith("Bearer ")
    assert params.sse_read_timeout.total_seconds() == 42


def test_failing_in_process_connect_is_logged_and_skipped(monkeypatch, caplog):
    async def boom(*a, **kw):
        raise RuntimeError("memory transport exploded")

    monkeypatch.setattr(chat_service, "_connect_in_process", boom)

    async def go():
        async with _connected_group(sse_read_timeout_s=30) as group:
            return len(group.sessions), len(group.tools)

    with caplog.at_level(logging.WARNING, logger=chat_service.logger.name):
        assert asyncio.run(go()) == (0, 0)
    assert any("'anton'" in r.getMessage() and "exploded" in r.getMessage() for r in caplog.records)


def test_session_and_server_task_are_torn_down_on_exit():
    async def go():
        before = {t for t in asyncio.all_tasks()}
        async with _connected_group(sse_read_timeout_s=30) as group:
            assert group.tools
        await asyncio.sleep(0)
        return [t for t in asyncio.all_tasks() if t not in before and not t.done()]

    assert asyncio.run(go()) == []


def test_body_exception_still_closes_cleanly():
    """A provider error mid-chat propagates (anyio wraps it in an ExceptionGroup,
    as the HTTP client's task group already did) and leaves no running task."""
    async def go():
        before = {t for t in asyncio.all_tasks()}
        with pytest.raises(BaseException) as ei:
            async with _connected_group(sse_read_timeout_s=30):
                raise ValueError("provider blew up")
        await asyncio.sleep(0)
        leaked = [t for t in asyncio.all_tasks() if t not in before and not t.done()]
        return ei.value, leaked

    exc, leaked = asyncio.run(go())
    assert "provider blew up" in repr(exc)
    assert leaked == []


def test_cancelled_chat_leaves_no_running_task():
    async def go():
        before = {t for t in asyncio.all_tasks()}
        entered = asyncio.Event()

        async def chat():
            async with _connected_group(sse_read_timeout_s=30):
                entered.set()
                await asyncio.sleep(60)

        task = asyncio.create_task(chat())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)
        return [t for t in asyncio.all_tasks() if t not in before and not t.done()]

    assert asyncio.run(go()) == []
