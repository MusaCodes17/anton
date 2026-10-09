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

# --- Records eligibility (R2.7 T3, reworked R8.1) --------------------------
# Records come in two lists (strava_stats.personal_bests):
#   - Race PBs: official results only — a run tagged Race/Parkrun, or one linked
#     to a planned race. Re-tagging a race to anything else removes it.
#   - Best efforts: the fastest whole runs of any kind except Intervals/Track,
#     whose rep distances would fake a record.
# Both are timed on ELAPSED time (R8.1), so a stop-heavy session's rests count
# against it — which retired T3's untagged elapsed/moving ratio guard.
RACE_RESULT_TAGS = frozenset({"Race", "Parkrun"})       # a Race PB
PB_EXCLUDED_TAGS = frozenset({"Intervals", "Track"})    # never a best effort


def is_valid_tag(tag: Optional[str]) -> bool:
    """True iff `tag` is a member of the vocabulary. `None` is not valid here —
    callers that allow clearing a tag handle `None` explicitly."""
    return tag in _VALID


# --- COROS-name tag inference (R2.7 T8) ------------------------------------
# Ordered keyword → tag rules for *suggesting* a tag from a COROS activity name.
# ORDER IS PRECEDENCE: the first matching rule wins, so the more specific/
# structured labels come first (a "parkrun" is Parkrun, not Race; an "easy long
# run" is Long Run, not Easy). This is a suggestion only — the sync agent
# surfaces it in the confirmation table and the runner confirms or overrides;
# it is NEVER auto-applied (C9). Keep this list aligned with ACTIVITY_TAGS.
_NAME_TAG_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("parkrun",), "Parkrun"),
    (("interval", "repeat"), "Intervals"),
    (("track",), "Track"),
    (("tempo", "threshold"), "Tempo"),
    (("long run", "long"), "Long Run"),
    (("trail",), "Trail"),
    (("race", "marathon"), "Race"),
    (("recovery", "easy", "jog"), "Easy"),
)


def suggest_tag_from_name(name: Optional[str]) -> Optional[str]:
    """Suggest an `activity_tag` from a COROS activity name via case-insensitive
    keyword matching (R2.7 T8). Returns a vocabulary tag or None when nothing
    matches (leave untagged). Suggestion only — the runner confirms it in the
    `sync_coros_runs` flow; never auto-applied (C9).
    """
    if not name:
        return None
    lowered = name.lower()
    for keywords, tag in _NAME_TAG_RULES:
        if any(kw in lowered for kw in keywords):
            return tag
    return None


def pb_exclusion_reason(tag: Optional[str]) -> Optional[str]:
    """Return a short reason string if a run with this tag is INELIGIBLE as a
    best effort, else None. Only Intervals/Track are excluded; untagged history
    (the 8-year archive) counts — the elapsed clock keeps stop-heavy runs honest.
    """
    if tag in PB_EXCLUDED_TAGS:
        return "interval/track session"
    return None
