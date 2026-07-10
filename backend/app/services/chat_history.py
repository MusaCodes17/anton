"""
Son of Anton conversation persistence (R2.6).

The store behind server-side chat memory — conversations moved off browser
localStorage so they're device-independent and (later, R3) readable by
server-side agents. The streaming endpoint (`POST /chat/message`) stays
stateless per request; this module is the separate CRUD path the client PUTs
to on stream-end.

Design (design_decisions C8-v2): both message arrays live as JSON on the row
(display_messages = rich UI shape, api_messages = LLM shape) rather than a
normalized messages table — at single-user scale (cap 50 conversations)
normalizing UI-shaped events would be speculative infra (CLAUDE.md §2.5). The
`id` is the client-generated UUID, so upsert is create-or-replace by that id.

Owns the writes to `chat_conversations`; commits within each function.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import ChatConversation

# Mirrors the old localStorage MAX_CONVERSATIONS — the cap is enforced here now
# so the store can't grow unbounded regardless of client behaviour.
MAX_CONVERSATIONS = 50


def _summary(conv: ChatConversation) -> dict:
    """List-panel projection — no message bodies, just what the sidebar needs."""
    return {
        "id": conv.id,
        "title": conv.title,
        "model": conv.model,
        "message_count": len(conv.display_messages or []),
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
    }


def list_conversations(db: Session) -> list[dict]:
    """All conversations as summaries, newest-updated first (sidebar order)."""
    rows = (
        db.query(ChatConversation)
        .order_by(ChatConversation.updated_at.desc())
        .all()
    )
    return [_summary(c) for c in rows]


def get_conversation(db: Session, conversation_id: str) -> ChatConversation:
    """Full conversation (both message arrays) for load-on-select.

    Raises:
        LookupError: no conversation with that id.
    """
    conv = db.get(ChatConversation, conversation_id)
    if conv is None:
        raise LookupError(f"Conversation {conversation_id!r} not found")
    return conv


def upsert_conversation(
    db: Session,
    conversation_id: str,
    *,
    title: Optional[str],
    model: Optional[str],
    display_messages: list,
    api_messages: list,
) -> ChatConversation:
    """Create-or-replace a conversation by its (client-generated) id.

    Mirrors the old whole-conversation localStorage save: the client PUTs the
    full state on stream-end, so this overwrites the message arrays wholesale.
    After writing, trims the oldest conversations beyond MAX_CONVERSATIONS so
    the store stays bounded (the server-side equivalent of the localStorage
    cap). Idempotent for a given id + payload.
    """
    conv = db.get(ChatConversation, conversation_id)
    if conv is None:
        conv = ChatConversation(id=conversation_id)
        db.add(conv)
    conv.title = title
    conv.model = model
    conv.display_messages = display_messages
    conv.api_messages = api_messages
    db.commit()
    db.refresh(conv)

    _trim_to_cap(db)
    return conv


def _trim_to_cap(db: Session) -> None:
    """Delete conversations beyond MAX_CONVERSATIONS, oldest-updated first."""
    stale = (
        db.query(ChatConversation)
        .order_by(ChatConversation.updated_at.desc())
        .offset(MAX_CONVERSATIONS)
        .all()
    )
    if not stale:
        return
    for conv in stale:
        db.delete(conv)
    db.commit()


def delete_conversation(db: Session, conversation_id: str) -> bool:
    """Delete a conversation. Idempotent — returns False if it didn't exist."""
    conv = db.get(ChatConversation, conversation_id)
    if conv is None:
        return False
    db.delete(conv)
    db.commit()
    return True
