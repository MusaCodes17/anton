"""Weather Strava recorded with an activity, projected out of ``raw_json`` (R5.4.2).

The Strava export carries weather for some activities under the keys
``"Weather Temperature"``, ``"Apparent Temperature"``, ``"Humidity"`` and
``"Wind Speed"``. Values arrive as numbers or numeric strings; missing is
``""`` or an absent key.

Units (checked on the runner's real export values, 2026-10-10 -- not assumed):
temperature is already **degrees C** (range -5.1 .. 33.9), humidity is a
**0-1 fraction** (max 0.91, so we multiply by 100 for ``humidity_pct``), wind
speed is **m/s** (max 8.6). Pure function, no I/O: shared by the importer and
the migration backfill so both agree on one conversion.
"""
from typing import Optional


def _num(value) -> Optional[float]:
    """Parse a number or numeric string; blank/missing/unparseable/NaN -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def weather_from_raw(raw: Optional[dict]) -> dict:
    """Typed weather fields from a Strava raw row.

    Returns ``{"weather_temp_c", "apparent_temp_c", "humidity_pct",
    "wind_speed_m_s"}`` -- floats or None per field. Temps and wind round to
    1 dp; humidity (fraction x 100) rounds to 0 dp.
    """
    raw = raw if isinstance(raw, dict) else {}
    temp = _num(raw.get("Weather Temperature"))
    apparent = _num(raw.get("Apparent Temperature"))
    humidity = _num(raw.get("Humidity"))
    wind = _num(raw.get("Wind Speed"))
    return {
        "weather_temp_c": round(temp, 1) if temp is not None else None,
        "apparent_temp_c": round(apparent, 1) if apparent is not None else None,
        "humidity_pct": float(round(humidity * 100)) if humidity is not None else None,
        "wind_speed_m_s": round(wind, 1) if wind is not None else None,
    }
