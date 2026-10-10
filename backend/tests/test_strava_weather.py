"""R5.4.2 -- Strava weather projection: pure parser + migration backfill."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.utils.strava_weather import weather_from_raw

BACKEND_ROOT = Path(__file__).resolve().parent.parent
_NONE = {"weather_temp_c": None, "apparent_temp_c": None, "humidity_pct": None, "wind_speed_m_s": None}


def test_numbers_and_numeric_strings():
    raw = {"Weather Temperature": 12.34, "Apparent Temperature": "10.06",
           "Humidity": 0.37, "Wind Speed": "3.26"}
    assert weather_from_raw(raw) == {
        "weather_temp_c": 12.3, "apparent_temp_c": 10.1, "humidity_pct": 37.0, "wind_speed_m_s": 3.3}


def test_humidity_fraction_to_percent_rounded_0dp():
    assert weather_from_raw({"Humidity": "0.915"})["humidity_pct"] == 92.0
    assert weather_from_raw({"Humidity": 0})["humidity_pct"] == 0.0


def test_blank_missing_and_none():
    assert weather_from_raw(None) == _NONE
    assert weather_from_raw({}) == _NONE
    assert weather_from_raw({"Weather Temperature": "", "Humidity": "  ", "Wind Speed": None}) == _NONE


def test_unparseable_and_nan_are_none():
    raw = {"Weather Temperature": "warm", "Apparent Temperature": float("nan"), "Wind Speed": True}
    assert weather_from_raw(raw) == _NONE


def test_partial_fields():
    out = weather_from_raw({"Weather Temperature": "-5.1"})
    assert out["weather_temp_c"] == -5.1 and out["wind_speed_m_s"] is None


def test_migration_backfills_strava_rows_only(tmp_path):
    db_path = tmp_path / "w.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}

    def alembic(*args):
        r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND_ROOT,
                           env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    alembic("upgrade", "c2d3e4f5a6b7")

    conn = sqlite3.connect(db_path)
    raw = json.dumps({"Weather Temperature": "21.5", "Humidity": "0.37", "Wind Speed": 2.26,
                      "Apparent Temperature": ""})
    conn.execute("INSERT INTO activities (source, strava_activity_id, raw_json) VALUES ('strava', 1, ?)", (raw,))
    conn.execute("INSERT INTO activities (source, strava_activity_id, raw_json) VALUES ('strava', 2, ?)", ("{}",))
    conn.execute("INSERT INTO activities (source, coros_activity_id, raw_json) VALUES ('coros', 'c1', ?)", (raw,))
    conn.commit(); conn.close()

    alembic("upgrade", "head")
    conn = sqlite3.connect(db_path)
    rows = {r[0]: r[1:] for r in conn.execute(
        "SELECT COALESCE(strava_activity_id, coros_activity_id), weather_temp_c, apparent_temp_c, "
        "humidity_pct, wind_speed_m_s FROM activities")}
    conn.close()
    assert rows[1] == (21.5, None, 37.0, 2.3)
    assert rows[2] == (None, None, None, None)
    assert rows["c1"] == (None, None, None, None)  # non-strava rows stay null
