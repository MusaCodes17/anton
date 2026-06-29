"""
Chat API — streaming endpoint that calls Claude (or OpenAI) with access to MCP tools.
"""
import json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import OwnedShoe
from app.services.chat_service import read_mcp_resource, stream_chat

router = APIRouter(prefix="/chat", tags=["chat"])

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str = DEFAULT_MODEL


@router.get("/providers")
def get_providers():
    """Returns available AI providers and their model lists. available is driven by API key presence."""
    return {
        "providers": {
            "anthropic": {
                "name": "Claude",
                "available": bool(os.getenv("ANTHROPIC_API_KEY")),
                "models": [
                    {
                        "id": "claude-sonnet-4-5",
                        "name": "Claude Sonnet",
                        "description": "Best quality",
                    },
                    {
                        "id": "claude-haiku-4-5-20251001",
                        "name": "Claude Haiku",
                        "description": "Fastest",
                    },
                ],
            },
            "openai": {
                "name": "ChatGPT",
                "available": bool(os.getenv("OPENAI_API_KEY")),
                "models": [
                    {
                        "id": "gpt-4o",
                        "name": "GPT-4o",
                        "description": "Best quality",
                    },
                    {
                        "id": "gpt-4o-mini",
                        "name": "GPT-4o Mini",
                        "description": "Fastest",
                    },
                ],
            },
            "google": {
                "name": "Gemini",
                "available": bool(os.getenv("GOOGLE_API_KEY")),
                "models": [
                    {
                        "id": "gemini-2.0-flash",
                        "name": "Gemini Flash",
                        "description": "Fastest",
                    },
                    {
                        "id": "gemini-2.0-pro",
                        "name": "Gemini Pro",
                        "description": "Best quality",
                    },
                ],
            },
        },
        "default_model": DEFAULT_MODEL,
    }


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


@router.post("/message")
async def chat_message(request: ChatRequest):
    """
    Stream a chat response as Server-Sent Events. Each event is a JSON object:
      {"type": "tool_call",   "tool": "..."}
      {"type": "tool_result", "tool": "...", "success": true}
      {"type": "text",        "content": "..."}
      {"type": "done"}
      {"type": "error",       "message": "..."}
    """
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    async def event_generator():
        async for event in stream_chat(messages, request.model):
            yield {"data": json.dumps(event)}

    return EventSourceResponse(event_generator())
