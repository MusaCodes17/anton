"""Pure pace conversion utilities. No app imports — safe to import
from models, services, and client modules alike.

Running pace is persisted as integer seconds-per-km (CLAUDE.md §6); the
"M:SS/km" strings these produce are presentation only. This module is the
single home for that conversion — previously duplicated in rotation,
the (since-removed Open-API) coros_client, and the (since-retired) ShoeRun.avg_pace proxy (R1.5c, dependency_graph §11.3).
"""
from __future__ import annotations

from typing import Optional


def seconds_to_pace(s_per_km: float) -> str:
    """Convert seconds/km to display string 'M:SS/km'.

    Accepts a float so callers can pass computed averages (e.g. total
    seconds / total km); the value is rounded to the nearest whole second.
    """
    total = round(s_per_km)
    mins, secs = divmod(total, 60)
    return f"{mins}:{secs:02d}/km"


def pace_to_seconds(pace_str: str) -> Optional[int]:
    """Parse 'M:SS/km' display string -> integer seconds/km.
    Returns None on malformed input.
    """
    try:
        mins_str, secs_str = pace_str.split('/')[0].strip().split(':')
        return int(mins_str) * 60 + int(secs_str)
    except (ValueError, AttributeError):
        return None
