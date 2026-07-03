"""
Strava bulk-export importer (§2 of the historical-import plan).

Parses the `activities.csv` from a Strava data export into normalized rows and
upserts them into `strava_activities`, idempotent on Strava's stable
`Activity ID`. Pure functions where possible; the CLI
(`app/scripts/import_strava.py`) is a thin wrapper.

Notes baked in from the verified export (do not re-derive):
- The CSV has DUPLICATE column headers. pandas suffixes the second occurrence
  with `.1`. `Distance` (first) is kilometers; `Distance.1` is meters. Use
  `Moving Time` (seconds) for pace. Keep `Max Heart Rate.1` (device summary).
- `Activity Date` is UTC, format "Jul 2, 2026, 11:08:07 PM". App run dates are
  America/Toronto; converting first is mandatory (145 evening runs shift day).
- Gear strings can carry a trailing space ("Neo Zen ") — always strip.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy.orm import Session

from app.models.models import StravaActivity

LOCAL_TZ = ZoneInfo("America/Toronto")
STRAVA_DATE_FORMAT = "%b %d, %Y, %I:%M:%S %p"

# Minimum distance for a meaningful average pace. Below this, moving_time /
# distance produces nonsense, so pace is left null.
MIN_PACE_DISTANCE_KM = 0.5


@dataclass
class StravaActivityRow:
    """One normalized activity, ready to upsert into strava_activities."""
    strava_activity_id: int
    activity_type: Optional[str]
    name: Optional[str]
    description: Optional[str]
    started_at_utc: Optional[datetime]
    started_at_local: Optional[datetime]
    run_date: Optional[date]
    distance_km: Optional[float]
    moving_time_s: Optional[int]
    elapsed_time_s: Optional[int]
    avg_hr: Optional[int]
    max_hr: Optional[int]
    avg_pace_s_per_km: Optional[int]
    elevation_gain_m: Optional[float]
    avg_cadence: Optional[float]
    calories: Optional[float]
    gear_name: Optional[str]
    fit_filename: Optional[str]
    grade_adjusted_distance_m: Optional[float]
    raw_json: dict = field(default_factory=dict)


@dataclass
class ImportStats:
    total: int = 0
    inserted: int = 0
    updated: int = 0
    runs: int = 0


def _clean(value):
    """pandas NaN / NaT / empty-string -> None; numpy scalars -> native Python."""
    if value is None:
        return None
    # pd.isna raises on array-likes; activity fields are all scalars here.
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    return value


def _to_int(value) -> Optional[int]:
    v = _clean(value)
    return int(round(v)) if v is not None else None


def _to_float(value) -> Optional[float]:
    v = _clean(value)
    return float(v) if v is not None else None


def _to_str(value) -> Optional[str]:
    v = _clean(value)
    return str(v) if v is not None else None


def _row_to_raw_json(row: pd.Series) -> dict:
    """Full CSV row as a JSON-safe dict — the 'ingest raw, model later' escape hatch."""
    out = {}
    for key, value in row.items():
        cleaned = _clean(value)
        if isinstance(cleaned, float) and (math.isnan(cleaned) or math.isinf(cleaned)):
            cleaned = None
        out[str(key)] = cleaned
    return out


def _parse_row(row: pd.Series) -> StravaActivityRow:
    raw_date = _clean(row.get("Activity Date"))
    started_utc = None
    started_local = None
    run_date = None
    if raw_date is not None:
        ts_utc = pd.to_datetime(raw_date, format=STRAVA_DATE_FORMAT, utc=True)
        ts_local = ts_utc.tz_convert(LOCAL_TZ)
        # Store naive datetimes (tz already applied) so SQLite comparisons and
        # the existing Date-typed run_date column line up with app conventions.
        started_utc = ts_utc.tz_localize(None).to_pydatetime()
        started_local = ts_local.tz_localize(None).to_pydatetime()
        run_date = ts_local.date()

    distance_km = _to_float(row.get("Distance"))  # first Distance column = km
    moving_time_s = _to_int(row.get("Moving Time"))
    elapsed_time_s = _to_int(row.get("Elapsed Time"))  # first Elapsed Time = seconds

    avg_pace_s_per_km = None
    if (
        distance_km is not None
        and distance_km >= MIN_PACE_DISTANCE_KM
        and moving_time_s is not None
        and moving_time_s > 0
    ):
        avg_pace_s_per_km = int(round(moving_time_s / distance_km))

    gear_name = _to_str(row.get("Activity Gear"))  # _clean already strips

    return StravaActivityRow(
        strava_activity_id=int(_clean(row.get("Activity ID"))),
        activity_type=_to_str(row.get("Activity Type")),
        name=_to_str(row.get("Activity Name")),
        description=_to_str(row.get("Activity Description")),
        started_at_utc=started_utc,
        started_at_local=started_local,
        run_date=run_date,
        distance_km=distance_km,
        moving_time_s=moving_time_s,
        elapsed_time_s=elapsed_time_s,
        avg_hr=_to_int(row.get("Average Heart Rate")),
        max_hr=_to_int(row.get("Max Heart Rate.1", row.get("Max Heart Rate"))),
        avg_pace_s_per_km=avg_pace_s_per_km,
        elevation_gain_m=_to_float(row.get("Elevation Gain")),
        avg_cadence=_to_float(row.get("Average Cadence")),
        calories=_to_float(row.get("Calories")),
        gear_name=gear_name,
        fit_filename=_to_str(row.get("Filename")),
        grade_adjusted_distance_m=_to_float(row.get("Grade Adjusted Distance")),
        raw_json=_row_to_raw_json(row),
    )


def parse_activities_csv(path: str) -> list[StravaActivityRow]:
    """
    Read a Strava export activities.csv into normalized rows. Imports ALL
    activity types (Run filtering happens downstream, at backfill time).

    Guards against Strava reordering the duplicate `Distance` columns in a
    future export: asserts km ≈ meters/1000 on the first row that has both.
    """
    df = pd.read_csv(path)

    if "Distance" in df.columns and "Distance.1" in df.columns:
        both = df[df["Distance"].notna() & df["Distance.1"].notna()]
        if len(both):
            sample = both.iloc[0]
            km, meters = float(sample["Distance"]), float(sample["Distance.1"])
            if meters > 0 and abs(km - meters / 1000.0) > max(0.05, km * 0.02):
                raise ValueError(
                    "Strava CSV column layout unexpected: first 'Distance' "
                    f"({km}) is not ~= 'Distance.1'/1000 ({meters / 1000.0}). "
                    "The duplicate-header km/meters assumption no longer holds."
                )

    return [_parse_row(row) for _, row in df.iterrows()]


def upsert_strava_activities(rows: list[StravaActivityRow], session: Session) -> ImportStats:
    """
    Insert or update strava_activities, idempotent on strava_activity_id.
    Re-running after a fresh export updates existing rows in place — never
    duplicates. Does not commit (caller owns the transaction).
    """
    stats = ImportStats(total=len(rows))

    existing = {
        a.strava_activity_id: a
        for a in session.query(StravaActivity)
        .filter(StravaActivity.strava_activity_id.in_([r.strava_activity_id for r in rows]))
        .all()
    } if rows else {}

    for r in rows:
        if r.activity_type == "Run":
            stats.runs += 1

        target = existing.get(r.strava_activity_id)
        if target is None:
            target = StravaActivity(strava_activity_id=r.strava_activity_id)
            session.add(target)
            stats.inserted += 1
        else:
            stats.updated += 1

        target.activity_type = r.activity_type
        target.name = r.name
        target.description = r.description
        target.started_at_utc = r.started_at_utc
        target.started_at_local = r.started_at_local
        target.run_date = r.run_date
        target.distance_km = r.distance_km
        target.moving_time_s = r.moving_time_s
        target.elapsed_time_s = r.elapsed_time_s
        target.avg_hr = r.avg_hr
        target.max_hr = r.max_hr
        target.avg_pace_s_per_km = r.avg_pace_s_per_km
        target.elevation_gain_m = r.elevation_gain_m
        target.avg_cadence = r.avg_cadence
        target.calories = r.calories
        target.gear_name = r.gear_name
        target.fit_filename = r.fit_filename
        target.grade_adjusted_distance_m = r.grade_adjusted_distance_m
        target.raw_json = r.raw_json

    return stats


def import_from_csv(path: str, session: Session) -> ImportStats:
    """Parse + upsert in one call, committing the transaction. Returns stats."""
    rows = parse_activities_csv(path)
    stats = upsert_strava_activities(rows, session)
    session.commit()
    return stats
