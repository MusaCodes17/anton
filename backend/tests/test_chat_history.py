"""
Tests for R2.6 conversation persistence (services/chat_history).

The rules, boundary-explicit:
  1. upsert is create-or-replace by the client id — a second upsert of the same
     id overwrites, never duplicates.
  2. the store is capped at MAX_CONVERSATIONS; the oldest-updated are trimmed,
     newest survive.
  3. get raises LookupError on a missing id; delete is idempotent.
"""
import pytest

from app.services import chat_history


def _upsert(db, cid, *, title="t", model="m", display=None, api=None):
    return chat_history.upsert_conversation(
        db,
        cid,
        title=title,
        model=model,
        display_messages=display if display is not None else [{"role": "user", "content": "hi"}],
        api_messages=api if api is not None else [{"role": "user", "content": "hi"}],
    )


def test_upsert_then_get_round_trip(db):
    _upsert(db, "abc", title="First", model="claude-haiku-4-5-20251001")
    conv = chat_history.get_conversation(db, "abc")
    assert conv.id == "abc"
    assert conv.title == "First"
    assert conv.model == "claude-haiku-4-5-20251001"
    assert conv.display_messages == [{"role": "user", "content": "hi"}]


def test_upsert_replaces_not_duplicates(db):
    _upsert(db, "abc", title="First", display=[{"role": "user", "content": "one"}])
    _upsert(db, "abc", title="Renamed", display=[{"role": "user", "content": "two"}])
    all_convs = chat_history.list_conversations(db)
    assert len(all_convs) == 1
    conv = chat_history.get_conversation(db, "abc")
    assert conv.title == "Renamed"
    assert conv.display_messages == [{"role": "user", "content": "two"}]


def test_list_is_summary_with_message_count(db):
    _upsert(db, "abc", display=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}])
    summaries = chat_history.list_conversations(db)
    assert summaries[0]["id"] == "abc"
    assert summaries[0]["message_count"] == 2
    # summary carries no message bodies
    assert "display_messages" not in summaries[0]


def test_cap_trims_oldest_keeps_newest(db):
    cap = chat_history.MAX_CONVERSATIONS
    # Insert cap + 5, each newer than the last (updated_at drives order).
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(cap + 5):
        conv = _upsert(db, f"c{i:03d}")
        # force a deterministic, increasing updated_at
        conv.updated_at = base + timedelta(minutes=i)
        db.commit()
    # trigger one more upsert so _trim_to_cap runs against the fixed timestamps
    newest = _upsert(db, "c999")
    newest.updated_at = base + timedelta(minutes=cap + 100)
    db.commit()
    chat_history._trim_to_cap(db)

    remaining = chat_history.list_conversations(db)
    assert len(remaining) == cap
    ids = {r["id"] for r in remaining}
    # the very first (oldest) must have been trimmed; the newest survives
    assert "c000" not in ids
    assert "c999" in ids


def test_get_missing_raises(db):
    with pytest.raises(LookupError):
        chat_history.get_conversation(db, "nope")


def test_delete_is_idempotent(db):
    _upsert(db, "abc")
    assert chat_history.delete_conversation(db, "abc") is True
    assert chat_history.delete_conversation(db, "abc") is False
    assert chat_history.list_conversations(db) == []
