"""The activity-tag controlled vocabulary — the backend-owned source of truth
(R2.7 T1). Pure: no app imports, so services, routers, models, and the MCP
prompt can all import it, and the frontend receives it from one endpoint
(`GET /api/activities/tags`) instead of keeping its own copy.

`activity_tag` is schema-grade: it governs PB eligibility (T3), race promotion
(T6), and the weekly-summary agent (R3.1). Do NOT grow this list casually — a
new tag is a data-model change, not a label tweak. Tags are user-set or
suggested from COROS activity names at sync time (T8) and confirmed by the
runner (never auto-applied — C9).
"""
from __future__ import annotations

from typing import Optional

# Ordered for display. The string values are the stored/served canonical form.
ACTIVITY_TAGS: tuple[str, ...] = (
    "Easy",
    "Long Run",
    "Recovery",
    "Tempo",
    "Intervals",
    "Track",
    "Workout",
    "Trail",
    "Parkrun",
    "Race",
)

_VALID = set(ACTIVITY_TAGS)


def is_valid_tag(tag: Optional[str]) -> bool:
    """True iff `tag` is a member of the vocabulary. `None` is not valid here —
    callers that allow clearing a tag handle `None` explicitly."""
    return tag in _VALID
