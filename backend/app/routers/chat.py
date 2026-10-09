"""
Chat API — streaming endpoint that calls Claude (or OpenAI) with access to MCP tools.
"""
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import OwnedShoe
from app.models.schemas import (
    ConversationResponse,
    ConversationSummary,
    ConversationUpsert,
)
from app.services import chat_history, chat_proposals
from app.services.chat_service import (
    PROVIDERS,
    call_tool_once,
    get_models,
    read_mcp_resource,
    stream_chat,
)
from app.services.rate_limit import chat_limiter

router = APIRouter(prefix="/chat", tags=["chat"])

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def enforce_chat_rate_limit(request: Request) -> None:
    """FastAPI dependency: throttle `POST /chat/message` per client so an
    authenticated-but-looping caller can't burn paid LLM credits (R2, the
    R2.1-adjacent throttle — SECURITY_PASS_PLAN §6). Keyed by client IP; on
    exceed it raises 429 with `Retry-After` before the stream starts. Auth is
    still the security boundary — this only bounds spend/loops."""
    client = request.client
    key = client.host if client else "unknown"
    result = chat_limiter.take(key)
    if not result.allowed:
        retry_after = max(1, round(result.retry_after_s))
        raise HTTPException(
            status_code=429,
            detail="Chat rate limit exceeded — please slow down.",
            headers={"Retry-After": str(retry_after)},
        )


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str = DEFAULT_MODEL


@router.get("/providers")
def get_providers():
    """Available AI providers and their models, grouped by provider.

    `available` is driven by API-key presence. The model catalog is
    single-sourced in chat_service.get_models() (R1.5d) — this endpoint only
    groups it by provider and layers on key availability.
    """
    providers: dict = {}
    for model in get_models():
        pkey = model["provider"]
        meta = PROVIDERS[pkey]
        bucket = providers.setdefault(pkey, {
            "name": meta["name"],
            "available": bool(os.getenv(meta["api_key_env"])),
            "models": [],
        })
        bucket["models"].append({
            "id": model["id"],
            "name": model["label"],
            "description": model["description"],
        })
    return {"providers": providers, "default_model": DEFAULT_MODEL}


@router.get("/resources")
def get_chat_resources(db: Session = Depends(get_db)):
    """
    Returns all MCP resources grouped for the @ mention picker.
    Static resources are hard-coded; My Shoes are queried directly from the DB.
    """
    static_items = [
        {"id": "shoes://rotation", "label": "My Shoe Rotation", "type": "resource", "uri": "shoes://rotation"},
        {"id": "shoes://deals/active", "label": "Active Deals", "type": "resource", "uri": "shoes://deals/active"},
        {"id": "shoes://retailers", "label": "Retailers", "type": "resource", "uri": "shoes://retailers"},
    ]

    shoes = (
        db.query(OwnedShoe)
        .filter(OwnedShoe.status == "active")
        .order_by(OwnedShoe.created_at.desc())
        .all()
    )
    shoe_items = []
    for s in shoes:
        label = f"{s.brand} {s.model}"
        if s.nickname:
            label = f"{s.brand} {s.model} — {s.nickname}"
        shoe_items.append({
            "id": f"shoes://owned/{s.id}",
            "label": label,
            "sublabel": f"{round(s.current_mileage)}km · {s.status.capitalize()}",
            "type": "resource",
            "uri": f"shoes://owned/{s.id}",
        })

    return {
        "groups": [
            {"label": "Rotation & Deals", "items": static_items},
            {"label": "My Shoes", "items": shoe_items},
        ]
    }


class ResourceReadRequest(BaseModel):
    uri: str


@router.post("/resource/read")
async def read_resource_endpoint(request: ResourceReadRequest):
    """Read a single MCP resource by URI and return its text content."""
    try:
        content = await read_mcp_resource(request.uri)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Extract first H1 as label
    label = request.uri.split("/")[-1]
    for line in content.split("\n"):
        if line.startswith("# "):
            label = line[2:].strip()
            break

    return {"uri": request.uri, "content": content, "label": label}


# ── Conversation persistence (R2.6) ─────────────────────────────────────────
# Server-side chat memory. The streaming endpoint below stays stateless; the
# client PUTs the full conversation here on stream-end.

@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(db: Session = Depends(get_db)):
    """All persisted conversations as summaries, newest-updated first."""
    return chat_history.list_conversations(db)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """One full conversation (both message arrays) for load-on-select."""
    try:
        return chat_history.get_conversation(db, conversation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
def upsert_conversation(
    conversation_id: str,
    payload: ConversationUpsert,
    db: Session = Depends(get_db),
):
    """Create-or-replace a conversation by its client-generated id."""
    return chat_history.upsert_conversation(
        db,
        conversation_id,
        title=payload.title,
        model=payload.model,
        display_messages=payload.display_messages,
        api_messages=payload.api_messages,
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """Delete a conversation. Idempotent — deleting a missing one is a no-op."""
    deleted = chat_history.delete_conversation(db, conversation_id)
    return {"success": True, "deleted": deleted}


# ── Confirmation cards (R7.2, C12) ──────────────────────────────────────────
# The stream holds write-tool calls as proposals; these run or decline one.
# The client sends only the id — the held arguments are the ones that run.

class ProposalCancel(BaseModel):
    # Set when the runner used Edit (the app's own form) instead of Confirm.
    edited_values: Optional[dict] = None


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str):
    """One proposal's current state — polled while a long tool runs."""
    try:
        return chat_proposals.to_dict(chat_proposals.get(proposal_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/proposals/{proposal_id}/confirm")
async def confirm_proposal(proposal_id: str):
    """Run the held call exactly as proposed. Idempotent: repeating it never
    runs the tool twice. status="executing" means poll GET for the result."""
    try:
        proposal = await chat_proposals.confirm(proposal_id, executor=call_tool_once)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return chat_proposals.to_dict(proposal)


@router.post("/proposals/{proposal_id}/cancel")
def cancel_proposal(proposal_id: str, payload: ProposalCancel | None = None):
    """Decline the held call; nothing runs."""
    try:
        proposal = chat_proposals.cancel(
            proposal_id, edited_values=payload.edited_values if payload else None
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return chat_proposals.to_dict(proposal)


@router.post("/message")
async def chat_message(request: ChatRequest, _rl: None = Depends(enforce_chat_rate_limit)):
    """
    Stream a chat response as Server-Sent Events. Each event is a JSON object:
      {"type": "tool_call",   "tool": "..."}
      {"type": "tool_result", "tool": "...", "success": true}
      {"type": "text",        "content": "..."}
      {"type": "proposal",    "proposal": {...}}   (a held write call — see /proposals)
      {"type": "done"}
      {"type": "error",       "message": "..."}
    """
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    async def event_generator():
        async for event in stream_chat(messages, request.model):
            yield {"data": json.dumps(event)}

    return EventSourceResponse(event_generator())
