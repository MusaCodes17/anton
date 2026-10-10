"""
Shoe suggestion for a pending COROS run (COROS direct sync §5).

Job: a deterministic, no-model port of the heuristic in the `sync_coros_runs` MCP
prompt (mcp_server/coros.py, "Step 3 — Suggest shoe assignment"), so the app's inbox and
Claude propose the same shoe for the same run. If you change a band here, change
that prompt text too (and vice-versa) — they are two renderings of one rule.

The rule (heuristic — a suggestion the runner overrides with one tap, C9):
1. Pace picks candidate shoe_types (PRIMARY signal), distance picks candidate
   shoe_types (SECONDARY). Bands are inclusive as written in the prompt, and
   deliberately overlap.
2. Types both signals agree on win; among ACTIVE shoes of those types the one with
   the lowest `current_mileage` is suggested (spreads wear), ties → lowest id.
3. If they conflict — or they agree but the rotation has no active shoe of that
   type — fall back to the union of both signals' types, same lowest-mileage pick.
4. Nothing in the rotation fits → no suggestion, and the reason says so
   explicitly rather than forcing a bad match.
Only `status == "active"` shoes are ever suggested: retired / for_sale never.
`trail` appears in no band, so a trail shoe is never auto-suggested (the prompt has
no trail rule; not invented here).

Commit ownership: read-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import OwnedShoe
from app.utils.pace import seconds_to_pace

# (lo_s_per_km, hi_s_per_km, types) — inclusive bounds; None = open-ended.
# Mirrors the prompt: <3:30 · 3:30–4:15 · 4:00–4:30 · 4:30–5:30 · >5:30.
_PACE_BANDS: list[tuple[Optional[int], Optional[int], frozenset[str]]] = [
    (None, 209, frozenset({"short_distance_racer", "intervals"})),
    (210, 255, frozenset({"tempo", "long_distance_racer"})),
    (240, 270, frozenset({"long_run"})),
    (270, 330, frozenset({"daily_trainer"})),
    (331, None, frozenset({"recovery", "daily_trainer"})),
]

# Distance bands (prompt): <5 · 5–16 · 16–22 · >21. The first is strictly below 5
# and the last strictly above 21; the middle two are inclusive and overlap at 16
# and 21–22, so distance_types() spells them out rather than using a table.
_DIST_SHORT = frozenset({"intervals", "short_distance_racer"})
_DIST_MID = frozenset({"daily_trainer"})
_DIST_UPPER_MID = frozenset({"tempo", "daily_trainer"})
_DIST_LONG = frozenset({"long_run", "long_distance_racer"})


@dataclass(frozen=True)
class ShoeSuggestion:
    shoe_id: Optional[int]
    reason: Optional[str]


def pace_types(avg_pace_s_per_km: int) -> frozenset[str]:
    out: set[str] = set()
    for lo, hi, types in _PACE_BANDS:
        if (lo is None or avg_pace_s_per_km >= lo) and (hi is None or avg_pace_s_per_km <= hi):
            out |= types
    return frozenset(out)


def distance_types(distance_km: float) -> frozenset[str]:
    out: set[str] = set()
    if distance_km < 5.0:
        out |= _DIST_SHORT
    if 5.0 <= distance_km <= 16.0:
        out |= _DIST_MID
    if 16.0 <= distance_km <= 22.0:
        out |= _DIST_UPPER_MID
    if distance_km > 21.0:
        out |= _DIST_LONG
    return frozenset(out)


def _names(types: frozenset[str]) -> str:
    return " / ".join(sorted(types))


def _pick(shoes: list[OwnedShoe], types: frozenset[str]) -> Optional[OwnedShoe]:
    pool = [s for s in shoes if s.shoe_type in types]
    # lowest mileage first; id breaks ties so the answer is deterministic
    return min(pool, key=lambda s: (s.current_mileage or 0.0, s.id)) if pool else None


def suggest_shoe(db: Session, *, distance_km: float, avg_pace_s_per_km: int) -> ShoeSuggestion:
    """Suggest an active owned shoe for a run, with a short stated reason."""
    shoes = db.query(OwnedShoe).filter(OwnedShoe.status == "active").all()
    p_types = pace_types(avg_pace_s_per_km)
    d_types = distance_types(distance_km)
    pace_s = seconds_to_pace(avg_pace_s_per_km)
    run = f"{pace_s}, {distance_km:.1f} km"

    agree = p_types & d_types
    if agree:
        shoe = _pick(shoes, agree)
        if shoe:
            return ShoeSuggestion(
                shoe.id,
                f"Pace and distance agree ({run}) → {_names(agree)}; lowest mileage ({shoe.current_mileage:.0f} km)."[:200],
            )

    union = p_types | d_types
    shoe = _pick(shoes, union)
    if shoe:
        why = ("no active shoe of the agreed type" if agree
               else f"pace suggests {_names(p_types)}, distance suggests {_names(d_types)}")
        return ShoeSuggestion(
            shoe.id,
            f"{run}: {why}; lowest mileage among them ({shoe.current_mileage:.0f} km)."[:200],
        )

    return ShoeSuggestion(None, f"No active shoe in your rotation fits {run} (looked for {_names(union)})."[:200])
