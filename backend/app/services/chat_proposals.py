"""
Confirmation cards for Son of Anton's write tools (roadmap §R7.2, decision C12).

When the embedded assistant calls a tool that changes data, the chat loop does
not run it. It hands the call to `create()`, which holds the exact tool name
and arguments server-side and returns a runner-facing summary; the stream then
ends with a `proposal` SSE event and the app renders a card. Only the runner's
tap runs the held call (`confirm()`), through the same MCP tool and so the same
sanctioned service path (`rotation.log_run`, `coros.confirm_run`, …). The
client sends back only the proposal id, never arguments — what is confirmed is
exactly what was proposed. This is C9 / INV-8 turned from prose into a control.

Held proposals live in this process's memory with a TTL. That is deliberate:
single Uvicorn worker (INV-9), personal scale, and a pending card that
outlives a restart simply reads "expired — ask again". Nothing here writes
domain data itself.

Gating is default-deny: any tool that isn't known read-only is held, so a new
MCP write tool is gated without anyone remembering to list it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.orm import Session

from app.models.models import OwnedShoe, Retailer, Shoe, ShoeRun

logger = logging.getLogger(__name__)

# Tools that never change data. Everything named get_* is read-only by the
# MCP server's naming convention; these are the read-only tools outside it.
READ_ONLY_TOOLS = frozenset({
    "scrape_health",
    "fetch_unsynced_coros_runs",
    "probe_retailer",
})

# Tools that write, but only data the runner ruled needs no confirmation card:
# sync_coros_now fills the "New runs" inbox (each run is still confirmed one by
# one) and saves COROS's fitness reading as-is (design decisions C13).
NO_CONFIRM_TOOLS = frozenset({
    "sync_coros_now",
})

PROPOSAL_TTL = timedelta(minutes=30)   # a card older than this can't be confirmed; ask again
CONFIRM_WAIT_S = 20.0                  # confirm() returns "executing" after this; the card polls
MAX_HELD = 200                         # defensive cap on the in-memory registry

# pending → executing → done; pending → cancelled | expired. done/cancelled/expired are terminal.
TERMINAL = frozenset({"done", "cancelled", "expired"})

Executor = Callable[[str, dict], Awaitable[tuple[str, bool]]]


@dataclass
class Proposal:
    """One held write-tool call awaiting the runner's decision."""
    id: str
    tool: str
    args: dict
    title: str
    fields: list[dict]                     # [{"label": ..., "value": ...}] in display order
    edit: Optional[dict]                   # prefill for the app's own form, when one exists
    created_at: datetime
    status: str = "pending"
    result: Optional[dict] = None          # the tool's JSON result once done
    edited_values: Optional[dict] = None   # set when the runner used Edit instead
    _task: Optional[asyncio.Task] = field(default=None, repr=False)


_proposals: dict[str, Proposal] = {}


def requires_confirmation(tool: str, args: dict) -> bool:
    """True when a tool call would change data and must wait for the runner.

    Default-deny: unknown tools are held. A call with `confirm=False` (the
    onboarding tools' preview mode) writes nothing, so it runs immediately.
    """
    if tool.startswith("get_") or tool in READ_ONLY_TOOLS or tool in NO_CONFIRM_TOOLS:
        return False
    if args.get("confirm") is False:
        return False
    return True


# ── Summaries ────────────────────────────────────────────────────────────────

def _shoe_label(shoe: OwnedShoe) -> str:
    label = f"{shoe.brand} {shoe.model}"
    return f"{label} — {shoe.nickname}" if shoe.nickname else label


def _km(value: Any) -> str:
    try:
        return f"{float(value):.1f} km"
    except (TypeError, ValueError):
        return str(value)


def _fields(*pairs: tuple[str, Any]) -> list[dict]:
    """Drop empty values so the card only shows what the call actually sets."""
    return [{"label": k, "value": str(v)} for k, v in pairs if v not in (None, "")]


def _owned(db: Session, owned_shoe_id: Any) -> Optional[OwnedShoe]:
    try:
        return db.get(OwnedShoe, int(owned_shoe_id))
    except (TypeError, ValueError):
        return None


def _run_fields(db: Session, args: dict, *, date_key: str) -> tuple[list[dict], Optional[OwnedShoe]]:
    shoe = _owned(db, args.get("owned_shoe_id"))
    mileage = None
    if shoe is not None:
        try:
            after = shoe.current_mileage + float(args.get("distance_km") or 0)
            mileage = f"{shoe.current_mileage:.1f} → {after:.1f} km"
        except (TypeError, ValueError):
            pass
    fields = _fields(
        ("Shoe", _shoe_label(shoe) if shoe else f"#{args.get('owned_shoe_id')} (not found)"),
        ("Date", args.get(date_key)),
        ("Distance", _km(args["distance_km"]) if args.get("distance_km") is not None else None),
        ("Pace", args.get("avg_pace")),
        ("Avg HR", f"{args['avg_hr']} bpm" if args.get("avg_hr") else None),
        ("Name", args.get("name")),
        ("Tag", args.get("activity_tag")),
        ("Notes", args.get("notes")),
        ("Shoe mileage", mileage),
    )
    return fields, shoe


def describe(db: Session, tool: str, args: dict) -> tuple[str, list[dict], Optional[dict]]:
    """Title, display fields and optional Edit prefill for a held call.

    Read-only DB lookups to put names on ids. Unknown tools fall back to the
    raw arguments, so a new write tool still gets an honest card.
    """
    if tool == "log_run_to_shoe":
        fields, shoe = _run_fields(db, args, date_key="run_date")
        edit = None
        if shoe is not None:
            edit = {
                "kind": "log_run",
                "shoe": {"id": shoe.id, "brand": shoe.brand, "model": shoe.model, "nickname": shoe.nickname},
                "values": {k: args.get(k) for k in ("distance_km", "run_date", "avg_pace", "avg_hr", "notes")},
            }
        return "Log run", fields, edit

    if tool == "confirm_coros_run":
        fields, _ = _run_fields(db, args, date_key="date")
        return "Log COROS run", fields, None

    if tool == "retire_shoe":
        shoe = _owned(db, args.get("owned_shoe_id"))
        return "Retire shoe", _fields(
            ("Shoe", _shoe_label(shoe) if shoe else f"#{args.get('owned_shoe_id')} (not found)"),
            ("Mileage", _km(shoe.current_mileage) if shoe else None),
        ), None

    if tool == "delete_shoe_run":
        run = None
        try:
            run = db.get(ShoeRun, int(args.get("run_id")))
        except (TypeError, ValueError):
            pass
        if run is None:
            return "Delete run", _fields(("Run", f"#{args.get('run_id')} (not found)")), None
        act = run.activity
        return "Delete run", _fields(
            ("Shoe", _shoe_label(run.owned_shoe) if run.owned_shoe else None),
            ("Date", act.run_date if act else None),
            ("Distance", _km(act.distance_km) if act and act.distance_km is not None else None),
        ), None

    if tool in ("add_shoe_note", "save_shoe_review"):
        shoe = _owned(db, args.get("owned_shoe_id"))
        text = args.get("body") if tool == "add_shoe_note" else args.get("review_text")
        return ("Add note" if tool == "add_shoe_note" else "Save review"), _fields(
            ("Shoe", _shoe_label(shoe) if shoe else f"#{args.get('owned_shoe_id')} (not found)"),
            ("Note" if tool == "add_shoe_note" else "Review", text),
        ), None

    if tool == "add_shoe":
        return "Track shoe", _fields(
            ("Shoe", f"{args.get('brand', '')} {args.get('model', '')}".strip()),
            ("MSRP", f"${args['msrp']}" if args.get("msrp") is not None else None),
            ("Target", f"${args['target_price']}" if args.get("target_price") is not None else None),
        ), None

    if tool == "delete_shoe":
        shoe = None
        try:
            shoe = db.get(Shoe, int(args.get("shoe_id")))
        except (TypeError, ValueError):
            pass
        return "Stop tracking shoe", _fields(
            ("Shoe", f"{shoe.brand} {shoe.model}" if shoe else f"#{args.get('shoe_id')} (not found)"),
        ), None

    if tool in ("onboard_retailer", "mark_retailer_unscrapable"):
        retailer = None
        try:
            retailer = db.get(Retailer, int(args.get("retailer_id")))
        except (TypeError, ValueError):
            pass
        name = retailer.name if retailer else f"#{args.get('retailer_id')} (not found)"
        if tool == "onboard_retailer":
            return "Onboard retailer", _fields(("Retailer", name), ("Platform", args.get("platform"))), None
        return "Mark retailer unscrapable", _fields(("Retailer", name), ("Reason", args.get("reason"))), None

    if tool == "trigger_scrape":
        target = f"Shoe #{args['shoe_id']}" if args.get("shoe_id") else "Every tracked shoe (20–30 min)"
        return "Run a scrape", _fields(("Scope", target)), None

    # Generic fallback: humanised name + every argument as given.
    title = tool.replace("_", " ").capitalize()
    return title, [
        {"label": k, "value": v if isinstance(v, str) else json.dumps(v)} for k, v in args.items()
    ], None


# ── Registry ─────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expire_stale() -> None:
    now = _now()
    for p in list(_proposals.values()):
        if p.status == "pending" and now - p.created_at > PROPOSAL_TTL:
            p.status = "expired"
        # Terminal proposals are kept for a TTL so a repeated tap or a poll
        # still gets the outcome, then dropped.
        if p.status in TERMINAL and now - p.created_at > 2 * PROPOSAL_TTL:
            _proposals.pop(p.id, None)


def create(db: Session, tool: str, args: dict) -> Proposal:
    """Hold one write-tool call and return it, summarised for the card.

    Reads only (names for ids); the caller owns the session. Does not run the tool.
    """
    _expire_stale()
    if len(_proposals) >= MAX_HELD:
        oldest = min(_proposals.values(), key=lambda p: p.created_at)
        _proposals.pop(oldest.id, None)
    title, fields, edit = describe(db, tool, args)
    proposal = Proposal(
        id=uuid.uuid4().hex,
        tool=tool,
        args=dict(args),
        title=title,
        fields=fields,
        edit=edit,
        created_at=_now(),
    )
    _proposals[proposal.id] = proposal
    logger.info("Held %s for confirmation (proposal %s)", tool, proposal.id)
    return proposal


def get(proposal_id: str) -> Proposal:
    """Raises LookupError when the id is unknown (never issued, or lost to a restart)."""
    _expire_stale()
    proposal = _proposals.get(proposal_id)
    if proposal is None:
        raise LookupError("This proposal has expired. Ask Son of Anton again.")
    return proposal


async def _execute(proposal: Proposal, executor: Executor) -> None:
    try:
        text, ok = await executor(proposal.tool, proposal.args)
        try:
            result = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            result = {"result": text}
        if not isinstance(result, dict):
            result = {"result": result}
        if not ok:
            result.setdefault("success", False)
        proposal.result = result
    except Exception as exc:  # isolate: a failed call is an outcome, not a crash
        logger.error("Confirmed %s (proposal %s) failed: %s", proposal.tool, proposal.id, exc)
        proposal.result = {"success": False, "error": str(exc)}
    proposal.status = "done"


async def confirm(proposal_id: str, *, executor: Executor, wait_s: float = CONFIRM_WAIT_S) -> Proposal:
    """Run the held call exactly as proposed — at most once.

    Idempotent: a second confirm while it runs waits on the same execution;
    after it finishes, returns the stored outcome without running it again.
    Returns with status "executing" if the tool outlives `wait_s` (a full
    scrape); the caller polls `get()`.

    Raises:
        LookupError: unknown id.
        ValueError: the proposal was cancelled or has expired.
    """
    proposal = get(proposal_id)
    if proposal.status in ("cancelled", "expired"):
        raise ValueError(f"This proposal was {proposal.status}; nothing was run.")
    if proposal.status == "pending":
        # Check-and-set with no await in between: atomic on the event loop.
        proposal.status = "executing"
        proposal._task = asyncio.create_task(_execute(proposal, executor))
    if proposal.status == "executing" and proposal._task is not None:
        try:
            await asyncio.wait_for(asyncio.shield(proposal._task), timeout=wait_s)
        except asyncio.TimeoutError:
            pass
    return proposal


def cancel(proposal_id: str, *, edited_values: Optional[dict] = None) -> Proposal:
    """Decline a held call. Nothing runs. `edited_values` records that the
    runner used the app's own form instead (Edit). Repeating it is a no-op.

    Raises:
        LookupError: unknown id.
        ValueError: the call already ran (or is running).
    """
    proposal = get(proposal_id)
    if proposal.status == "cancelled":
        return proposal
    if proposal.status != "pending":
        raise ValueError(f"This proposal is already {proposal.status}.")
    proposal.status = "cancelled"
    proposal.edited_values = edited_values
    return proposal


# ── Wire shapes ──────────────────────────────────────────────────────────────

def transcript_note(proposal: Proposal) -> str:
    """The assistant-side line recorded in the conversation history, so the
    model later knows what it proposed (the card itself isn't text)."""
    return (
        f"[Proposed {proposal.tool}({json.dumps(proposal.args)}) — shown to the runner as a "
        "confirmation card; waiting for their decision.]"
    )


def followup_message(proposal: Proposal) -> Optional[str]:
    """The hidden user-turn text that reports the runner's decision back to the
    model, or None while undecided."""
    if proposal.status == "done":
        return (
            f"[Confirmation card] The runner tapped Confirm. {proposal.tool} ran with the proposed "
            f"arguments. Result: {json.dumps(proposal.result)}. Report the outcome briefly; if "
            "success is false, give the exact error. Mention any threshold or checkpoint in the result."
        )
    if proposal.status == "cancelled" and proposal.edited_values is not None:
        return (
            f"[Confirmation card] The runner chose Edit and did it themselves in the app's form "
            f"instead (values: {json.dumps(proposal.edited_values)}). The proposed {proposal.tool} "
            "call was NOT run. Acknowledge briefly; don't call the tool again."
        )
    if proposal.status == "cancelled":
        return (
            f"[Confirmation card] The runner tapped Cancel. {proposal.tool} was NOT run and nothing "
            "was written. Acknowledge briefly and ask whether they want to change anything."
        )
    return None


def to_dict(proposal: Proposal) -> dict:
    """The card's view of a proposal: SSE `proposal` event payload and REST body."""
    return {
        "id": proposal.id,
        "tool": proposal.tool,
        "title": proposal.title,
        "fields": proposal.fields,
        "edit": proposal.edit,
        "status": proposal.status,
        "result": proposal.result,
        "transcript_note": transcript_note(proposal),
        "followup_message": followup_message(proposal),
    }
