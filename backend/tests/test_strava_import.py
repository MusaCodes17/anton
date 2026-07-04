"""
Parser tests (§7): duplicate headers, UTC→local date shift, missing HR,
missing gear, trailing-space gear, sub-0.5km pace suppression, and the
km ≈ meters/1000 guard against a future column reorder.
"""
from datetime import date

import pytest

from app.services import strava_import

# Column order mirrors the real export's quirk: Distance / Max Heart Rate
# appear twice, so pandas suffixes the second with `.1`. First Distance = km,
# second = meters; Max Heart Rate.1 is the device-summary value we keep.
_HEADER = (
    "Activity ID,Activity Date,Activity Name,Activity Type,Activity Description,"
    "Elapsed Time,Distance,Max Heart Rate,Activity Gear,Filename,"
    "Moving Time,Distance,Max Heart Rate,Average Heart Rate,"
    "Elevation Gain,Average Cadence,Calories,Grade Adjusted Distance"
)

_ROWS = [
    # tz-shift (UTC Jul 3 03:00 → Toronto Jul 2 23:00) + trailing-space gear + max_hr picks .1
    '1001,"Jul 3, 2026, 03:00:00 AM",Late Night,Run,,3600,10.00,181,"Neo Zen ",activities/1.fit.gz,3000,10000,180,,120.0,88.0,500.0,10100.0',
    # missing HR (avg + both max blank)
    '1002,"Jun 15, 2026, 02:00:00 PM",Tempo,Run,,1800,5.00,,Nike Streakfly,activities/2.fit.gz,1700,5000,,,10.0,90.0,300.0,5050.0',
    # missing gear
    '1003,"Jun 10, 2026, 01:00:00 PM",No Gear,Run,,2000,8.00,150,,activities/3.fit.gz,1900,8000,150,140,20.0,89.0,400.0,8080.0',
    # non-run (imported, but activity_type != Run)
    '1004,"Jun 09, 2026, 10:00:00 AM",Bike,Ride,,3600,30.00,140,,activities/4.fit.gz,3500,30000,140,130,100.0,,600.0,30000.0',
    # sub-0.5km run → pace suppressed
    '1005,"Jun 08, 2026, 12:00:00 PM",Warmup,Run,,300,0.30,120,Nike Streakfly,activities/5.fit.gz,200,300,120,110,1.0,80.0,20.0,305.0',
]


def _write_csv(tmp_path, rows) -> str:
    p = tmp_path / "activities.csv"
    p.write_text("\n".join([_HEADER, *rows]) + "\n")
    return str(p)


def _by_id(rows):
    return {r.strava_activity_id: r for r in rows}


def test_parses_all_rows_including_non_runs(tmp_path):
    rows = strava_import.parse_activities_csv(_write_csv(tmp_path, _ROWS))
    assert len(rows) == 5
    assert _by_id(rows)[1004].activity_type == "Ride"


def test_utc_to_local_date_shift(tmp_path):
    r = _by_id(strava_import.parse_activities_csv(_write_csv(tmp_path, _ROWS)))[1001]
    # UTC calendar date is Jul 3, but the local run_date must be Jul 2.
    assert r.started_at_utc.date() == date(2026, 7, 3)
    assert r.run_date == date(2026, 7, 2)
    assert r.started_at_local.hour == 23


def test_trailing_space_gear_is_stripped(tmp_path):
    r = _by_id(strava_import.parse_activities_csv(_write_csv(tmp_path, _ROWS)))[1001]
    assert r.gear_name == "Neo Zen"


def test_duplicate_headers_km_vs_meters(tmp_path):
    r = _by_id(strava_import.parse_activities_csv(_write_csv(tmp_path, _ROWS)))[1001]
    assert r.distance_km == 10.0            # first Distance column = km
    assert r.raw_json["Distance.1"] == 10000.0  # second = meters, preserved raw


def test_max_hr_prefers_second_column(tmp_path):
    r = _by_id(strava_import.parse_activities_csv(_write_csv(tmp_path, _ROWS)))[1001]
    assert r.max_hr == 180  # Max Heart Rate.1, not the first (181)


def test_missing_hr_is_none(tmp_path):
    r = _by_id(strava_import.parse_activities_csv(_write_csv(tmp_path, _ROWS)))[1002]
    assert r.avg_hr is None
    assert r.max_hr is None


def test_missing_gear_is_none(tmp_path):
    r = _by_id(strava_import.parse_activities_csv(_write_csv(tmp_path, _ROWS)))[1003]
    assert r.gear_name is None


def test_pace_computed_and_suppressed_below_half_km(tmp_path):
    rows = _by_id(strava_import.parse_activities_csv(_write_csv(tmp_path, _ROWS)))
    assert rows[1001].avg_pace_s_per_km == 300   # 3000s / 10km
    assert rows[1005].avg_pace_s_per_km is None   # 0.30km < 0.5km floor


def test_column_reorder_guard_raises(tmp_path):
    # Swap km/meters so the first Distance is ~10000 and second ~10 — the
    # km ≈ meters/1000 invariant breaks and parsing must refuse.
    bad = (
        '2001,"Jun 08, 2026, 12:00:00 PM",Bad,Run,,300,10000.0,120,'
        'Nike Streakfly,activities/x.fit.gz,200,10.0,120,110,1.0,80.0,20.0,305.0'
    )
    with pytest.raises(ValueError):
        strava_import.parse_activities_csv(_write_csv(tmp_path, [bad]))


def test_upsert_is_idempotent(tmp_path, db):
    path = _write_csv(tmp_path, _ROWS)
    s1 = strava_import.import_from_csv(path, db)
    assert s1.total == 5 and s1.inserted == 5 and s1.runs == 4
    s2 = strava_import.import_from_csv(path, db)
    assert s2.inserted == 0 and s2.updated == 5
    from app.models.models import Activity
    assert db.query(Activity).filter(Activity.source == "strava").count() == 5  # no duplicates
