"""
Confirmation cards for Son of Anton's write tools (R7.2, decision C12).

The rules under test:
  - default-deny gating: get_* and the listed read tools run, everything else
    is held; confirm=False previews run;
  - the chat loop never runs a held call — it emits a `proposal` and ends the turn;
  - Confirm runs exactly the held call, at most once (double tap is a no-op);
  - Cancel runs nothing; cancelled/expired proposals can't be confirmed;
  - INV-8 end to end: a chat-proposed run log writes nothing until Confirm,
    then exactly one activity with the right mileage delta.
"""
import asyncio
import json
from contextlib import contextmanager
from datetime import date, timedelta

import pytest

from app import mcp_server
from app.models.models import Activity, OwnedShoe, ShoeRun
from app.services import chat_proposals as cp
from app.services.chat_service import BaseLLMProvider, _ToolCall


@pytest.fixture(autouse=True)
def _clean_registry():
    cp._proposals.clear()
    yield
    cp._proposals.clear()


@pytest.fixture()
def shoe(db):
    s = OwnedShoe(
        brand="Adidas", model="Evo SL", nickname="Teal", shoe_type="daily_trainer",
        status="active", starting_mileage=0.0, current_mileage=500.0,
    )
    db.add(s)
    db.commit()
    return s


def _log_args(shoe_id, km=12.4):
    return {"owned_shoe_id": shoe_id, "distance_km": km, "run_date": "2026-10-09", "avg_pace": "4:30/km"}


def run(coro):
    return asyncio.run(coro)


# ── Gating ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tool,args,held", [
    ("get_owned_shoes", {}, False),
    ("get_deals", {"size": "9"}, False),
    ("scrape_health", {}, False),
    ("fetch_unsynced_coros_runs", {"days_back": 7}, False),
    ("probe_retailer", {"retailer_id": 1}, False),
    ("sync_coros_now", {}, False),          # inbox + fitness only; runs still confirmed (C13)
    ("record_athlete_metrics", {"vo2max": 59}, True),
    ("log_run_to_shoe", {"owned_shoe_id": 1}, True),
    ("confirm_coros_run", {}, True),
    ("retire_shoe", {"owned_shoe_id": 1}, True),
    ("trigger_scrape", {}, True),
    ("onboard_retailer", {"retailer_id": 1, "confirm": False}, False),  # preview writes nothing
    ("onboard_retailer", {"retailer_id": 1, "confirm": True}, True),
    ("some_future_tool", {}, True),  # default-deny: unknown tools are held
])
def test_requires_confirmation(tool, args, held):
    assert cp.requires_confirmation(tool, args) is held


# ── Summaries ────────────────────────────────────────────────────────────────

def test_log_run_card_names_the_shoe_and_mileage_change(db, shoe):
    p = cp.create(db, "log_run_to_shoe", _log_args(shoe.id))
    fields = {f["label"]: f["value"] for f in p.fields}
    assert p.title == "Log run"
    assert fields["Shoe"] == "Adidas Evo SL — Teal"
    assert fields["Distance"] == "12.4 km"
    assert fields["Shoe mileage"] == "500.0 → 512.4 km"
    assert "Avg HR" not in fields  # unset args are not shown
    assert p.edit["kind"] == "log_run" and p.edit["values"]["distance_km"] == 12.4


def test_unknown_shoe_still_gets_an_honest_card(db):
    p = cp.create(db, "log_run_to_shoe", _log_args(999))
    assert {"label": "Shoe", "value": "#999 (not found)"} in p.fields
    assert p.edit is None


def test_unknown_tool_falls_back_to_raw_args(db):
    p = cp.create(db, "some_future_tool", {"x": 1, "name": "y"})
    assert p.title == "Some future tool"
    assert {"label": "x", "value": "1"} in p.fields


# ── Confirm / cancel lifecycle ───────────────────────────────────────────────

def _counting_executor(calls, result=None):
    async def executor(name, args):
        calls.append((name, dict(args)))
        return json.dumps(result or {"success": True}), True
    return executor


def test_confirm_runs_exactly_the_proposed_call_once(db, shoe):
    p = cp.create(db, "log_run_to_shoe", _log_args(shoe.id))
    calls = []
    ex = _counting_executor(calls)

    async def go():
        first = await cp.confirm(p.id, executor=ex)
        second = await cp.confirm(p.id, executor=ex)  # double tap
        return first, second

    first, second = run(go())
    assert calls == [("log_run_to_shoe", _log_args(shoe.id))]
    assert first.status == second.status == "done"
    assert "tapped Confirm" in cp.followup_message(first)


def test_concurrent_confirms_share_one_execution(db, shoe):
    p = cp.create(db, "log_run_to_shoe", _log_args(shoe.id))
    calls = []

    async def slow(name, args):
        calls.append(name)
        await asyncio.sleep(0.05)
        return json.dumps({"success": True}), True

    async def go():
        return await asyncio.gather(cp.confirm(p.id, executor=slow), cp.confirm(p.id, executor=slow))

    results = run(go())
    assert calls == ["log_run_to_shoe"]
    assert all(r.status == "done" for r in results)


def test_long_tool_returns_executing_then_finishes(db):
    p = cp.create(db, "trigger_scrape", {})

    async def slow(name, args):
        await asyncio.sleep(0.2)
        return json.dumps({"success": True}), True

    async def go():
        early = await cp.confirm(p.id, executor=slow, wait_s=0.01)
        status_early = early.status
        await asyncio.sleep(0.3)
        return status_early, cp.get(p.id).status

    assert run(go()) == ("executing", "done")


def test_failed_tool_is_an_outcome_not_a_crash(db, shoe):
    p = cp.create(db, "log_run_to_shoe", _log_args(shoe.id))

    async def boom(name, args):
        raise RuntimeError("loopback down")

    done = run(cp.confirm(p.id, executor=boom))
    assert done.status == "done"
    assert done.result == {"success": False, "error": "loopback down"}


def test_cancel_runs_nothing_and_blocks_confirm(db, shoe):
    p = cp.create(db, "log_run_to_shoe", _log_args(shoe.id))
    calls = []
    cp.cancel(p.id)
    assert cp.cancel(p.id).status == "cancelled"  # repeat is a no-op
    with pytest.raises(ValueError):
        run(cp.confirm(p.id, executor=_counting_executor(calls)))
    assert calls == []
    assert "NOT run" in cp.followup_message(cp.get(p.id))


def test_cannot_cancel_after_confirm(db, shoe):
    p = cp.create(db, "log_run_to_shoe", _log_args(shoe.id))
    run(cp.confirm(p.id, executor=_counting_executor([])))
    with pytest.raises(ValueError):
        cp.cancel(p.id)


def test_edit_records_the_form_values(db, shoe):
    p = cp.create(db, "log_run_to_shoe", _log_args(shoe.id))
    cp.cancel(p.id, edited_values={"distance_km": 12.0})
    msg = cp.followup_message(cp.get(p.id))
    assert "Edit" in msg and '"distance_km": 12.0' in msg


def test_expired_proposal_cannot_be_confirmed(db, shoe):
    p = cp.create(db, "log_run_to_shoe", _log_args(shoe.id))
    p.created_at -= cp.PROPOSAL_TTL + timedelta(seconds=1)
    with pytest.raises(ValueError):
        run(cp.confirm(p.id, executor=_counting_executor([])))
    assert cp.get(p.id).status == "expired"


def test_unknown_id_is_lookup_error():
    with pytest.raises(LookupError):
        cp.get("nope")


# ── The chat loop holds write calls ──────────────────────────────────────────

class _ScriptedProvider(BaseLLMProvider):
    """One turn that calls the given tools; a second turn would say 'done'."""

    def __init__(self, calls):
        self.turns = [calls, []]
        self.appended = False

    def _tool_schema(self, tool):
        return tool

    async def _check_configured(self, queue):
        return True

    def _prepare_messages(self, initial_messages, model, tool_schemas):
        return {}

    async def _stream_turn(self, state, model, tool_schemas, queue):
        calls = self.turns.pop(0)
        for c in calls:
            await queue.put({"type": "tool_call", "tool": c.name})
        return calls

    def _append_tool_results(self, state, tool_calls, results):
        self.appended = True


def _drain(queue):
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


def test_loop_holds_write_runs_reads_and_ends_turn():
    provider = _ScriptedProvider([
        _ToolCall(id="1", name="get_owned_shoes", input={}),
        _ToolCall(id="2", name="log_run_to_shoe", input={"owned_shoe_id": 1}),
    ])
    executed = []

    async def call_mcp_tool(name, args):
        executed.append(name)
        return "{}", True

    def hold(name, args):
        return {"id": "p1", "tool": name} if name.startswith("log_") else None

    async def go():
        q = asyncio.Queue()
        await provider.run([], "m", [], q, call_mcp_tool, hold_for_confirmation=hold)
        return _drain(q)

    events = run(go())
    assert executed == ["get_owned_shoes"]          # the write never ran
    types = [e["type"] for e in events]
    assert types[-2:] == ["proposal", "done"]
    assert events[-2]["proposal"] == {"id": "p1", "tool": "log_run_to_shoe"}
    assert provider.appended is False                # the model was not resumed


# ── INV-8 end to end: nothing is written until Confirm ───────────────────────

@pytest.fixture()
def in_process_mcp(db, monkeypatch):
    """Run confirmed calls through the real MCP tool, in process, on the test DB."""
    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server, "get_session", fake_session)

    async def executor(name, args):
        out = await mcp_server.mcp.call_tool(name, args)
        content = out[0] if isinstance(out, tuple) else out
        return "\n".join(c.text for c in content if getattr(c, "type", None) == "text"), True
    return executor


def _runs(db):
    return db.query(Activity).count(), db.query(ShoeRun).count()


def test_proposed_run_writes_once_on_confirm(db, shoe, in_process_mcp):
    p = cp.create(db, "log_run_to_shoe", _log_args(shoe.id, km=12.4))
    assert _runs(db) == (0, 0)  # proposing writes nothing

    async def go():
        first = await cp.confirm(p.id, executor=in_process_mcp)
        await cp.confirm(p.id, executor=in_process_mcp)  # double tap
        return first

    done = run(go())
    db.expire_all()
    assert done.result["success"] is True, done.result
    assert _runs(db) == (1, 1)
    assert db.get(OwnedShoe, shoe.id).current_mileage == pytest.approx(512.4)
    assert db.query(Activity).one().run_date == date(2026, 10, 9)


def test_cancelled_run_writes_nothing(db, shoe, in_process_mcp):
    p = cp.create(db, "log_run_to_shoe", _log_args(shoe.id))
    cp.cancel(p.id)
    with pytest.raises(ValueError):
        run(cp.confirm(p.id, executor=in_process_mcp))
    db.expire_all()
    assert _runs(db) == (0, 0)
    assert db.get(OwnedShoe, shoe.id).current_mileage == 500.0


def test_system_prompt_carries_toronto_date():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.services.chat_service import _date_context

    today = datetime.now(ZoneInfo("America/Toronto")).date().isoformat()
    assert today in _date_context()
