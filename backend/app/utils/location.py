"""Start-location helpers (R5.4.1).

Privacy rule: only a rounded start point (lat/lng + a human label such as
"Montreal Run") is ever stored on an activity -- never tracks or polylines --
and MCP outputs expose the label, not the coordinates, by default. Every
writer rounds through `round_coord` so the rule lives in one place.
"""
from typing import Optional

# 3 decimals ~ 100 m: enough for weather lookups and "where did I run", not an
# address. Most runs start at home and the data is readable by LLM clients, so
# we deliberately keep less precision than the source provides.
COORD_DECIMALS = 3


def round_coord(value: Optional[float]) -> Optional[float]:
    """Round a latitude/longitude to COORD_DECIMALS; None passes through."""
    if value is None:
        return None
    return round(float(value), COORD_DECIMALS)
