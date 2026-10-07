"""
Shoe suggestion for a pending COROS run (COROS direct sync §5).

§4 seam: the poller calls `suggest_shoe` for every new run. The heuristic itself
lands in §5; until then it suggests nothing (a suggestion is optional by design —
the runner always decides, C9).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ShoeSuggestion:
    shoe_id: Optional[int]
    reason: Optional[str]


def suggest_shoe(db: Session, *, distance_km: float, avg_pace_s_per_km: int) -> ShoeSuggestion:
    return ShoeSuggestion(None, None)
