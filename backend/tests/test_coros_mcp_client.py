"""COROS direct sync §3 — typed MCP client: parsing contract + transport policy.

Fixtures are real responses captured in the §1 spike (coordinates redacted).
Tests pin the *contract*: units, label-id-as-string, loud failure on format
drift (never silent nulls), and retry only on network/5xx. The opt-in live
smoke test (COROS_LIVE=1) is skipped in CI.
"""
import json
import os
from datetime import date
from pathlib import Path

import pytest
import requests

from app.services.coros_connection import CorosAuthError
from app.services.coros_mcp_client import (
    CorosApiError,
    CorosContractError,
    CorosMcpClient,
    merge_detail,
    parse_activity_detail,
    parse_fitness_overview,
    parse_sport_records,
)

FIX = Path(__file__).parent / "fixtures" / "coros"


def _fixture_text(name: str) -> str:
    return json.loads((FIX / name).read_text())["result"]["content"][0]["text"]


LIST_TEXT = _fixture_text("query_sport_records.json")
DETAIL_TEXT = _fixture_text("get_activity_detail.json")
FITNESS_TEXT = _fixture_text("fitness_overview.json")


# --- list parsing: units and shapes --------------------------------------------

def test_list_fixture_parses_all_records_with_exact_units():
    runs = parse_sport_records(LIST_TEXT)
    assert len(runs) == 14
    r = runs[0]
    assert r.label_id == "480858305181286402" and isinstance(r.label_id, str)
    assert r.sport_type == 100
    assert r.run_date == date(2026, 10, 6)       # printed date used as-is, not derived from the timestamp
    assert r.distance_km == 12.53
    assert r.moving_time_s == 52 * 60 + 39       # "52:39" is M:SS
    assert r.avg_pace_s_per_km == 4 * 60 + 12    # "4:12 /km" -> seconds per km
    assert r.avg_hr == 171 and r.calories == 710.0
    assert (r.start_timestamp, r.end_timestamp) == (1791333579, 1791336739)
    assert r.has_detail is False and r.elapsed_time_s is None


def test_h_mm_ss_durations_and_long_run():
    long_run = next(r for r in parse_sport_records(LIST_TEXT) if r.distance_km == 30.02)
    assert long_run.moving_time_s == 2 * 3600 + 43 * 60 + 10


def test_two_runs_on_the_same_date_stay_distinct():
    runs = parse_sport_records(LIST_TEXT)
    same = [r for r in runs if r.run_date == date(2026, 9, 30)]
    assert len(same) == 2 and same[0].label_id != same[1].label_id


def test_empty_range_is_an_empty_list_not_an_error():
    assert parse_sport_records('"No sport records found from 2020-01-01 to 2020-01-02."') == []


def test_unwrapped_plain_text_also_parses():
    plain = json.loads(LIST_TEXT) if LIST_TEXT.lstrip().startswith('"') else LIST_TEXT
    assert len(parse_sport_records(plain)) == 14


def test_missing_optional_hr_is_none_not_error():
    text = LIST_TEXT.replace("Avg HR: 171 bpm | ", "", 1)
    assert parse_sport_records(text)[0].avg_hr is None


# --- list parsing: loud failures -------------------------------------------------

def test_record_count_mismatch_fails_loudly():
    with pytest.raises(CorosContractError, match="header says 15"):
        parse_sport_records(LIST_TEXT.replace("(14 records)", "(15 records)"))


def test_missing_required_field_names_the_field_and_label():
    broken = LIST_TEXT.replace("Average Pace: 4:12 /km", "Avg Speed: 14.3 km/h", 1)
    with pytest.raises(CorosContractError, match=r"labelId 480858305181286402.*Average Pace"):
        parse_sport_records(broken)


def test_unrecognized_response_fails_loudly():
    with pytest.raises(CorosContractError, match="unrecognized"):
        parse_sport_records('"Something entirely different happened."')


def test_pace_unit_change_is_caught():
    with pytest.raises(CorosContractError, match="unit change"):
        parse_sport_records(LIST_TEXT.replace("Average Pace: 4:12 /km", "Average Pace: 0:04 /km", 1))


def test_distance_unit_change_is_caught():
    with pytest.raises(CorosContractError, match="unit change"):
        parse_sport_records(LIST_TEXT.replace("Distance: 12.53 km", "Distance: 12530.00 km", 1))


# --- detail ---------------------------------------------------------------------

def test_detail_fixture_exact_units():
    d = parse_activity_detail(DETAIL_TEXT)
    assert d.distance_km == 12.53
    assert d.moving_time_s == 3159 and d.elapsed_time_s == 3159
    assert d.avg_pace_s_per_km == 252
    assert d.avg_hr == 171
    assert d.avg_cadence == 186.0
    assert d.elevation_gain_m == 60.0       # "60 m / 48 m": gain, not loss
    assert d.calories == 710.0 and d.training_load == 113.0
    assert d.training_focus == "Base"


def test_detail_optional_lines_absent_become_none():
    text = DETAIL_TEXT
    for needle in ("Average Cadence: 186 spm", "Training Focus: Base", "Elevation Gain / Loss: 60 m / 48 m"):
        text = text.replace(needle, "")
    d = parse_activity_detail(text)
    assert d.avg_cadence is None and d.training_focus is None and d.elevation_gain_m is None
    assert d.training_load == 113.0


def test_detail_anomaly_advisory_is_a_contract_error():
    advisory = '"Tool call anomalies detected. High risk of session context pollution. Resolution Strategy: 1. Initialize a new session"'
    with pytest.raises(CorosContractError, match="Workout Time"):
        parse_activity_detail(advisory)


def test_merge_detail_attaches_fields():
    run = parse_sport_records(LIST_TEXT)[0]
    merged = merge_detail(run, parse_activity_detail(DETAIL_TEXT))
    assert merged.has_detail and merged.elapsed_time_s == 3159 and merged.elevation_gain_m == 60.0
    assert merged.training_focus == "Base" and merged.label_id == run.label_id


def test_merge_detail_rejects_mismatched_report():
    other = parse_sport_records(LIST_TEXT)[1]  # 14.19 km vs the 12.53 km detail
    with pytest.raises(CorosContractError, match="detail"):
        merge_detail(other, parse_activity_detail(DETAIL_TEXT))


# --- transport ------------------------------------------------------------------

class Resp:
    def __init__(self, status=200, body=None, text=None, ctype="application/json"):
        self.status_code = status
        self.text = text if text is not None else json.dumps(body)
        self.headers = {"content-type": ctype}


def ok(text):
    return Resp(body={"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": text}], "isError": False}})


class Script:
    """Replays queued responses/exceptions; records each request."""

    def __init__(self, *items):
        self.items, self.calls = list(items), []

    def __call__(self, url, *, headers, json, timeout):
        self.calls.append({"url": url, "headers": headers, "json": json})
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(*items, sleeps=None):
    s = Script(*items)
    sl = sleeps if sleeps is not None else []
    return CorosMcpClient(lambda: "tok-123", url="https://c.test/mcp", post=s, sleep=sl.append), s, sl


def test_list_runs_sends_the_quirks():
    c, s, _ = client(ok(LIST_TEXT))
    runs = c.list_runs(date(2026, 9, 23), date(2026, 10, 7))
    assert len(runs) == 14
    req = s.calls[0]
    args = req["json"]["params"]["arguments"]
    assert req["json"]["params"]["name"] == "querySportRecords"
    assert args["sportTypeCodes"] == [100, 101, 102, 103]
    assert (args["startDate"], args["endDate"]) == ("20260923", "20261007")
    assert "timezone" not in args                      # tool has no such argument
    assert req["headers"]["Authorization"] == "Bearer tok-123"
    assert "event-stream" in req["headers"]["Accept"]


def test_get_run_detail_passes_label_as_string():
    c, s, _ = client(ok(DETAIL_TEXT))
    c.get_run_detail("480858305181286402", 100)
    assert s.calls[0]["json"]["params"]["arguments"] == {"labelId": "480858305181286402", "sportType": 100}


def test_fetch_run_end_to_end():
    run = parse_sport_records(LIST_TEXT)[0]
    c, _, _ = client(ok(DETAIL_TEXT))
    assert c.fetch_run(run).has_detail


def test_unknown_tool_is_a_contract_error():
    c, _, _ = client(Resp(body={"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "Unknown tool", "data": "Tool not found"}}))
    with pytest.raises(CorosContractError, match="contract changed"):
        c.list_runs(date(2026, 10, 1), date(2026, 10, 7))


def test_tool_level_error_is_api_error():
    c, _, _ = client(Resp(body={"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "\"boom\""}], "isError": True}}))
    with pytest.raises(CorosApiError, match="boom"):
        c.list_runs(date(2026, 10, 1), date(2026, 10, 7))


def test_401_raises_auth_error_without_retry():
    c, s, sleeps = client(Resp(401, text=""))
    with pytest.raises(CorosAuthError):
        c.list_runs(date(2026, 10, 1), date(2026, 10, 7))
    assert len(s.calls) == 1 and sleeps == []


def test_4xx_is_never_retried():
    c, s, sleeps = client(Resp(400, text="bad"))
    with pytest.raises(CorosApiError):
        c.list_runs(date(2026, 10, 1), date(2026, 10, 7))
    assert len(s.calls) == 1 and sleeps == []


def test_5xx_retries_with_backoff_then_succeeds():
    c, s, sleeps = client(Resp(503, text=""), Resp(502, text=""), ok(LIST_TEXT))
    assert len(c.list_runs(date(2026, 10, 1), date(2026, 10, 7))) == 14
    assert len(s.calls) == 3 and sleeps == [1.0, 3.0]


def test_network_errors_retry_then_raise_when_exhausted():
    c, s, sleeps = client(requests.ConnectionError("x"), requests.Timeout("y"), requests.ConnectionError("z"))
    with pytest.raises(requests.ConnectionError):
        c.list_runs(date(2026, 10, 1), date(2026, 10, 7))
    assert len(s.calls) == 3 and len(sleeps) == 2


def test_sse_framed_response_decodes():
    body = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": '"No sport records found from a to b."'}], "isError": False}}
    c, _, _ = client(Resp(text=f"event: message\ndata: {json.dumps(body)}\n\n", ctype="text/event-stream"))
    assert c.list_runs(date(2026, 10, 1), date(2026, 10, 7)) == []


def test_non_json_body_is_a_contract_error():
    c, _, _ = client(Resp(text="<html>gateway</html>"))
    with pytest.raises(CorosContractError, match="non-JSON"):
        c.list_runs(date(2026, 10, 1), date(2026, 10, 7))


# --- opt-in live smoke (COROS_LIVE=1; uses the spike's saved token, never in CI) -----

SPIKE_STATE = Path(__file__).resolve().parents[2] / "scripts" / "spikes" / ".coros_spike_state.json"


@pytest.mark.skipif(not (os.getenv("COROS_LIVE") and SPIKE_STATE.exists()), reason="opt-in live smoke test")
def test_live_smoke_returns_normalized_runs():
    token = json.loads(SPIKE_STATE.read_text())["tok"]["access_token"]
    c = CorosMcpClient(lambda: token)
    runs = c.list_runs(date.today().replace(day=1), date.today())
    assert runs, "expected at least one run this month"
    full = c.fetch_run(runs[0])
    assert full.has_detail and full.elapsed_time_s >= full.moving_time_s - 1


# --- fitness overview (R8.4.1) --------------------------------------------------

def test_fitness_fixture_exact_units():
    f = parse_fitness_overview(FITNESS_TEXT)
    assert (f.vo2max, f.running_level) == (59.0, 97.0)
    assert f.threshold_pace_s_per_km == 3 * 60 + 24              # "3:24 /km"
    # keys match the July snapshot / PredictionsCard; "16:17" is M:SS, "2:27:44" H:MM:SS
    assert f.race_predictions == {"5.0": 16 * 60 + 17, "10.0": 33 * 60 + 27,
                                  "21.0975": 3600 + 12 * 60 + 29, "42.195": 2 * 3600 + 27 * 60 + 44}


def test_fitness_missing_lines_are_none_not_errors():
    text = "Fitness Assessment Overview\n=====\n\nVO2max: 59\nMarathon Prediction: 2:27:44\n"
    f = parse_fitness_overview(text)
    assert f.vo2max == 59.0 and f.running_level is None and f.threshold_pace_s_per_km is None
    assert f.race_predictions == {"42.195": 8864}


def test_fitness_with_no_metrics_has_no_predictions_dict():
    f = parse_fitness_overview("Fitness Assessment Overview\n=====\n")
    assert f == type(f)(None, None, None, None)


@pytest.mark.parametrize("line", [
    "VO2max: --",
    "Running Level: high",
    "Threshold Pace: 3:24 /mi",
    "Threshold Pace: 0:30 /km",            # outside sane pace bounds
    "Marathon Prediction: 2h27m",
])
def test_fitness_garbled_present_line_fails_loudly(line):
    with pytest.raises(CorosContractError):
        parse_fitness_overview(f"Fitness Assessment Overview\n=====\n\n{line}\n")


def test_fitness_unrecognized_header_fails_loudly():
    with pytest.raises(CorosContractError, match="header"):
        parse_fitness_overview("No fitness assessment available")


def test_fitness_overview_calls_the_tool_with_no_arguments():
    c, s, _ = client(ok(FITNESS_TEXT))
    assert c.fitness_overview().vo2max == 59.0
    assert s.calls[0]["json"]["params"] == {"name": "queryFitnessAssessmentOverview", "arguments": {}}


# --- location (R5.4.1) ------------------------------------------------------------

def test_list_fixture_parses_location_label_and_full_precision_coordinates():
    for r in parse_sport_records(LIST_TEXT):
        assert r.location_label == "Montreal Run"
        assert (r.start_lat, r.start_lng) == (45.501689, -73.567256)   # rounding is storage's job


_NO_LOC = ('"Sport Records — 2026-10-06 to 2026-10-06 (1 records)\\n\\n'
           '1. Indoor Run — 2026-10-06\\n'
           '   Time Window: startTimestamp=1791333579 | endTimestamp=1791336739\\n'
           '   Duration: 52:39 | Distance: 12.53 km\\n'
           '   Average Pace: 4:12 /km | Avg HR: 171 bpm | Calories: 710 kcal\\n'
           '   LabelId: 480858305181286402 | SportType: 100"')


def test_record_without_location_lines_gets_none():
    (r,) = parse_sport_records(_NO_LOC)
    assert (r.location_label, r.start_lat, r.start_lng) == (None, None, None)


def test_garbled_coordinates_line_is_a_loud_contract_error():
    bad = _NO_LOC.replace("   Time Window", "   Start Coordinates: somewhere north\\n   Time Window", 1)
    with pytest.raises(CorosContractError):
        parse_sport_records(bad)
