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

# --- Personal-best eligibility (R2.7 T3) -----------------------------------
# The PB algorithm bands whole-activity times; a stop-heavy interval session can
# otherwise fake a distance record. Tags are the clean intentional signal; the
# elapsed-time ratio is the fallback for untagged history (the 8-year archive).
PB_EXCLUDED_TAGS = frozenset({"Intervals", "Track"})   # never set a PB
PB_ALWAYS_INCLUDED_TAGS = frozenset({"Race", "Parkrun"})  # always eligible
# Everything else tagged (Easy/Long Run/Recovery/Tempo/Trail/Workout) is eligible:
# a slow long run won't break a 5k PB, and a tempo that does is legitimate.

# Untagged runs: flag as suspicious when they stop a lot — elapsed ≫ moving.
PB_ELAPSED_RATIO = 1.5  # elapsed_time_s > 1.5 × moving_time_s → excluded


def is_valid_tag(tag: Optional[str]) -> bool:
    """True iff `tag` is a member of the vocabulary. `None` is not valid here —
    callers that allow clearing a tag handle `None` explicitly."""
    return tag in _VALID


def pb_exclusion_reason(
    tag: Optional[str],
    elapsed_time_s: Optional[int],
    moving_time_s: Optional[int],
) -> Optional[str]:
    """Return a short reason string if this run is INELIGIBLE for personal-best
    consideration, else None (eligible).

    - Tagged Intervals/Track → excluded ("interval/track session").
    - Tagged Race/Parkrun and other run tags → eligible.
    - Untagged → excluded only when stop-heavy (elapsed > 1.5×moving); the ratio
      needs both times, so an untagged run missing either is treated as eligible.
    """
    if tag in PB_EXCLUDED_TAGS:
        return "interval/track session"
    if tag is not None:
        return None  # any other vocabulary tag (Race/Parkrun/Easy/...) is eligible
    # Untagged: the elapsed-time guard.
    if elapsed_time_s and moving_time_s and elapsed_time_s > PB_ELAPSED_RATIO * moving_time_s:
        return "stop-heavy untagged run"
    return None
