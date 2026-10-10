"""
Typed client for the COROS MCP server (COROS direct sync §3, roadmap R5.7).

The ONLY place that speaks MCP to COROS. Pure transport + parsing: no DB, no
OAuth flow — it is handed a `token_provider` (see services/coros_connection.py
`get_access_token`) and returns normalized `CorosRun`s.

Why this is a parser and not a JSON mapper (R5.7 spike; design_decisions C11):
COROS tool results are human-formatted TEXT inside `content[0].text` (itself a
JSON-encoded string), and no tool declares an outputSchema. So every field is
pulled out with an anchored regex, and the contract is enforced loudly:
- a required field that's missing raises `CorosContractError` naming the field —
  we never write nulls for something COROS used to send;
- the "(N records)" header must equal the parsed record count;
- an unknown tool (JSON-RPC -32602/-32601) or an anomaly message in place of a
  detail report is a contract error, not an empty result;
- units are sanity-bounded (pace, distance) so a silent unit change fails here.
Optional fields (HR, calories, cadence, elevation, training load/focus) become
None only when their line is absent — treadmill runs legitimately lack some.

Quirks encoded (from the R5.7 spike): running = sport codes 100-103; dates are
`YYYYMMDD`; the per-record date printed by COROS IS the run date (Toronto local
for this account) and is used as-is — never re-derived from startTimestamp;
`labelId` is an 18-digit id kept as a STRING; the list endpoint has no
`timezone` argument; the server is stateless so no initialize handshake is made
(verified live 2026-10-07: tools/call works without it).

Retry policy: network errors and 5xx retry with backoff (3 attempts); 4xx never
retry. A 401 raises `CorosAuthError` (caller marks reauth / refreshes).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

import requests

from app.services.coros_connection import CorosAuthError, mcp_url

logger = logging.getLogger(__name__)

RUNNING_SPORT_CODES = [100, 101, 102, 103]  # outdoor, indoor, trail, track
HTTP_TIMEOUT_S = 30
MAX_ATTEMPTS = 3
BACKOFF_S = (1.0, 3.0)
LIST_LIMIT = 100

# Unit sanity bounds — a COROS scale/unit change must fail here, not corrupt data.
_PACE_BOUNDS_S_PER_KM = (90, 3600)
_MAX_DISTANCE_KM = 400.0
_DETAIL_DISTANCE_TOLERANCE_KM = 0.05  # list vs detail rounding


class CorosContractError(Exception):
    """COROS's response no longer matches what this client was written against."""


class CorosApiError(Exception):
    """COROS refused the request (4xx / tool-level error). Not retried."""


@dataclass(frozen=True)
class CorosRun:
    """One COROS run, normalized. Units live in names (CLAUDE.md §5).

    List fields are always present; detail fields are None until `with_detail`.
    `label_id` is a string (18 digits — beyond JS safe-integer range).
    """
    label_id: str
    sport_type: int
    run_date: date                      # as printed by COROS (Toronto local); not derived
    distance_km: float
    moving_time_s: int                  # list "Duration" == detail "Workout Time"
    avg_pace_s_per_km: int
    avg_hr: Optional[int]
    calories: Optional[float]
    start_timestamp: int
    end_timestamp: int
    # --- detail (getActivityDetail) ---
    elapsed_time_s: Optional[int] = None
    elevation_gain_m: Optional[float] = None
    avg_cadence: Optional[float] = None
    training_load: Optional[float] = None
    training_focus: Optional[str] = None
    has_detail: bool = False


@dataclass(frozen=True)
class CorosRunDetail:
    distance_km: float
    moving_time_s: int
    elapsed_time_s: int
    avg_pace_s_per_km: int
    avg_hr: Optional[int]
    avg_cadence: Optional[float]
    elevation_gain_m: Optional[float]
    calories: Optional[float]
    training_load: Optional[float]
    training_focus: Optional[str]


# ---------------------------------------------------------------- parsing (pure)

def _unwrap_text(text: str) -> str:
    """Tool text arrives as a JSON string literal ("...\\n...") — decode it."""
    t = text.strip()
    if t.startswith('"'):
        try:
            decoded = json.loads(t)
            if isinstance(decoded, str):
                return decoded
        except ValueError:
            pass
    return t


def parse_duration_s(s: str, field: str) -> int:
    parts = s.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        raise CorosContractError(f"{field}: unparseable duration {s!r}")
    if len(nums) == 2:
        m, sec = nums
        return m * 60 + sec
    if len(nums) == 3:
        h, m, sec = nums
        return h * 3600 + m * 60 + sec
    raise CorosContractError(f"{field}: unexpected duration shape {s!r}")


def _pace_s(s: str, field: str) -> int:
    sec = parse_duration_s(s, field)
    lo, hi = _PACE_BOUNDS_S_PER_KM
    if not lo <= sec <= hi:
        raise CorosContractError(f"{field}: pace {s!r} ({sec}s/km) outside sane bounds — unit change?")
    return sec


def _distance_km(s: str, field: str) -> float:
    d = float(s)
    if not 0 <= d <= _MAX_DISTANCE_KM:
        raise CorosContractError(f"{field}: distance {d} km outside sane bounds — unit change?")
    return d


def _req(pattern: str, block: str, field: str, ctx: str) -> re.Match:
    m = re.search(pattern, block)
    if not m:
        raise CorosContractError(f"{ctx}: required field '{field}' not found (COROS format change?)")
    return m


_RECORD_HEAD = re.compile(r"^\s*\d+\.\s+.+?\s+[—-]\s+(\d{4}-\d{2}-\d{2})\s*$", re.M)


def parse_sport_records(text: str) -> list[CorosRun]:
    """Parse a querySportRecords result. Returns [] for COROS's explicit
    'No sport records found' message; anything unrecognized raises."""
    body = _unwrap_text(text)
    if re.match(r"\s*No sport records found", body):
        return []
    header = re.search(r"Sport Records\b.*?\((\d+) records?\)", body)
    if not header:
        raise CorosContractError(f"querySportRecords: unrecognized response header: {body[:120]!r}")
    expected = int(header.group(1))

    heads = list(_RECORD_HEAD.finditer(body))
    runs: list[CorosRun] = []
    for i, h in enumerate(heads):
        block = body[h.start(): heads[i + 1].start() if i + 1 < len(heads) else len(body)]
        ctx = f"querySportRecords record #{i + 1}"
        ids = _req(r"LabelId:\s*(\d+)\s*\|\s*SportType:\s*(\d+)", block, "LabelId/SportType", ctx)
        ctx = f"{ctx} (labelId {ids.group(1)})"
        win = _req(r"startTimestamp=(\d+)\s*\|\s*endTimestamp=(\d+)", block, "Time Window", ctx)
        dur = _req(r"Duration:\s*([\d:]+)\s*\|\s*Distance:\s*([\d.]+)\s*km", block, "Duration/Distance", ctx)
        pace = _req(r"Average Pace:\s*([\d:]+)\s*/km", block, "Average Pace", ctx)
        hr = re.search(r"Avg HR:\s*(\d+)\s*bpm", block)
        cal = re.search(r"Calories:\s*([\d.]+)\s*kcal", block)
        runs.append(CorosRun(
            label_id=ids.group(1),
            sport_type=int(ids.group(2)),
            run_date=date.fromisoformat(h.group(1)),
            distance_km=_distance_km(dur.group(2), ctx),
            moving_time_s=parse_duration_s(dur.group(1), ctx),
            avg_pace_s_per_km=_pace_s(pace.group(1), ctx),
            avg_hr=int(hr.group(1)) if hr else None,
            calories=float(cal.group(1)) if cal else None,
            start_timestamp=int(win.group(1)),
            end_timestamp=int(win.group(2)),
        ))
    if len(runs) != expected:
        raise CorosContractError(
            f"querySportRecords: header says {expected} records but parsed {len(runs)} (format change?)")
    return runs


def parse_activity_detail(text: str) -> CorosRunDetail:
    body = _unwrap_text(text)
    ctx = "getActivityDetail"
    # COROS answers some bad requests with a 200 + an 'anomalies' advisory instead
    # of an error; the absence of the report's required lines catches that too.
    wt = _req(r"Workout Time:\s*([\d:]+)", body, "Workout Time", ctx)
    tt = _req(r"Total Time:\s*([\d:]+)", body, "Total Time", ctx)
    dist = _req(r"Distance:\s*([\d.]+)\s*km", body, "Distance", ctx)
    pace = _req(r"(?m)^Average Pace:\s*([\d:]+)\s*/km", body, "Average Pace", ctx)
    hr = re.search(r"(?m)^Average Heart Rate:\s*(\d+)\s*bpm", body)
    cad = re.search(r"(?m)^Average Cadence:\s*([\d.]+)\s*spm", body)
    elev = re.search(r"(?m)^Elevation Gain / Loss:\s*(-?[\d.]+)\s*m\s*/\s*(-?[\d.]+)\s*m", body)
    cal = re.search(r"(?m)^Calories:\s*([\d.]+)\s*kcal", body)
    load = re.search(r"(?m)^Training Load:\s*([\d.]+)", body)
    focus = re.search(r"(?m)^Training Focus:\s*(.+?)\s*$", body)
    return CorosRunDetail(
        distance_km=_distance_km(dist.group(1), ctx),
        moving_time_s=parse_duration_s(wt.group(1), ctx),
        elapsed_time_s=parse_duration_s(tt.group(1), ctx),
        avg_pace_s_per_km=_pace_s(pace.group(1), ctx),
        avg_hr=int(hr.group(1)) if hr else None,
        avg_cadence=float(cad.group(1)) if cad else None,
        elevation_gain_m=float(elev.group(1)) if elev else None,
        calories=float(cal.group(1)) if cal else None,
        training_load=float(load.group(1)) if load else None,
        training_focus=focus.group(1) if focus else None,
    )


# queryActivityFitFileDownloadUrls (R8.2): "1. <labelId>.fit" then the URL on
# the next line. Anchored on the label so another run's file can't be taken.
def parse_fit_url(text: str, label_id: str) -> str:
    """The FIT download URL for `label_id` from a queryActivityFitFileDownloadUrls
    result. The URL is an unsigned S3 link (anyone holding it can download the
    run, GPS track included): callers fetch it and drop it — never store or log it.
    Raises CorosContractError if the response doesn't carry one.
    """
    body = _unwrap_text(text)
    m = re.search(
        rf"^\s*\d+\.\s+{re.escape(str(label_id))}\.fit\s*\n\s*(https://\S+/{re.escape(str(label_id))}\.fit)\s*$",
        body, re.MULTILINE,
    )
    if not m:
        # No response excerpt in the message: it could carry another run's URL.
        raise CorosContractError(f"queryActivityFitFileDownloadUrls: no FIT URL for {label_id} (response shape changed?)")
    return m.group(1)


# queryFitnessAssessmentOverview (R8.4.1): one "Label: value" line per metric.
# COROS returns only today's values (no history, no date argument), as whole
# numbers. The prediction keys match the July snapshot and PredictionsCard.
_FITNESS_HEADER = re.compile(r"^\s*Fitness Assessment Overview\b")
_FITNESS_PREDICTIONS = (
    ("5 km", "5.0"),
    ("10 km", "10.0"),
    ("Half Marathon", "21.0975"),
    ("Marathon", "42.195"),
)


@dataclass(frozen=True)
class CorosFitness:
    """The runner's current COROS fitness assessment. A metric COROS can't
    assess yet is omitted from its report and is None here."""
    vo2max: Optional[float]
    running_level: Optional[float]
    threshold_pace_s_per_km: Optional[int]
    race_predictions: Optional[dict]   # {"5.0": seconds, ...}; None when COROS gave none


def _fitness_line(body: str, label: str) -> Optional[str]:
    """The value after `label:` on its own line, or None if the line is absent."""
    m = re.search(rf"(?m)^{re.escape(label)}:[ \t]*(.*?)\s*$", body)
    return m.group(1) if m else None


def parse_fitness_overview(text: str) -> CorosFitness:
    """Parse a queryFitnessAssessmentOverview result. A missing line is None
    (COROS omits what it can't assess); a present line whose value doesn't
    parse raises CorosContractError — a rewording must be loud, never a null."""
    body = _unwrap_text(text)
    ctx = "queryFitnessAssessmentOverview"
    if not _FITNESS_HEADER.match(body):
        raise CorosContractError(f"{ctx}: unrecognized response header: {body[:120]!r}")

    def number(label: str) -> Optional[float]:
        raw = _fitness_line(body, label)
        if raw is None:
            return None
        if not re.fullmatch(r"\d+(?:\.\d+)?", raw):
            raise CorosContractError(f"{ctx}: {label} {raw!r} is not a number (format change?)")
        return float(raw)

    threshold = _fitness_line(body, "Threshold Pace")
    if threshold is not None:
        m = re.fullmatch(r"([\d:]+)\s*/km", threshold)
        if not m:
            raise CorosContractError(f"{ctx}: Threshold Pace {threshold!r} is not M:SS /km (unit change?)")
        threshold_s: Optional[int] = _pace_s(m.group(1), f"{ctx} Threshold Pace")
    else:
        threshold_s = None

    predictions: dict[str, int] = {}
    for label, key in _FITNESS_PREDICTIONS:
        raw = _fitness_line(body, f"{label} Prediction")
        if raw is not None:
            predictions[key] = parse_duration_s(raw, f"{ctx} {label} Prediction")

    return CorosFitness(
        vo2max=number("VO2max"),
        running_level=number("Running Level"),
        threshold_pace_s_per_km=threshold_s,
        race_predictions=predictions or None,
    )


def merge_detail(run: CorosRun, detail: CorosRunDetail) -> CorosRun:
    """Attach detail to a list record. The detail text carries no id or date, so
    the only cross-check available is distance — a mismatch means we paired the
    wrong report (or units drifted), and is a contract error, not a warning."""
    if abs(run.distance_km - detail.distance_km) > _DETAIL_DISTANCE_TOLERANCE_KM:
        raise CorosContractError(
            f"labelId {run.label_id}: list distance {run.distance_km} km != detail {detail.distance_km} km")
    return dataclasses.replace(
        run,
        elapsed_time_s=detail.elapsed_time_s,
        elevation_gain_m=detail.elevation_gain_m,
        avg_cadence=detail.avg_cadence,
        training_load=detail.training_load,
        training_focus=detail.training_focus,
        has_detail=True,
    )


# ---------------------------------------------------------------- transport

class CorosMcpClient:
    """
    `token_provider` returns a valid access token per call (so a long-lived client
    never holds a stale one). `post` / `sleep` are injectable seams for tests.
    """

    def __init__(
        self,
        token_provider: Callable[[], str],
        *,
        url: Optional[str] = None,
        post: Optional[Callable[..., requests.Response]] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._token = token_provider
        self._url = url or mcp_url()
        self._post = post or requests.post
        self._sleep = sleep
        self._next_id = 0

    # -- public API -------------------------------------------------------

    def list_runs(self, start_date: date, end_date: date, *, limit: int = LIST_LIMIT) -> list[CorosRun]:
        """Runs between the dates inclusive, newest first, WITHOUT detail."""
        text = self._call_tool("querySportRecords", {
            "startDate": start_date.strftime("%Y%m%d"),
            "endDate": end_date.strftime("%Y%m%d"),
            "sportTypeCodes": RUNNING_SPORT_CODES,
            "minDistanceKm": None, "maxDistanceKm": None,
            "minDurationMinutes": None, "maxDurationMinutes": None,
            "maxAveragePace": None, "locationKeyword": None,
            "limit": limit,
        })
        runs = parse_sport_records(text)
        if len(runs) >= limit:
            # Possible truncation: surface it rather than silently dropping runs.
            logger.warning("COROS list returned %d records (= limit); older runs may be cut off", len(runs))
        return runs

    def get_run_detail(self, label_id: str, sport_type: int = 100) -> CorosRunDetail:
        text = self._call_tool("getActivityDetail", {"labelId": str(label_id), "sportType": sport_type})
        return parse_activity_detail(text)

    def fit_url(self, label_id: str, sport_type: int = 100) -> str:
        """The run's original FIT file URL (R8.2 best efforts). Counts against
        COROS's daily FIT download limit — callers ration it. Ask by labelId:
        the date-range form of this tool proved unreliable in the spike."""
        text = self._call_tool("queryActivityFitFileDownloadUrls", {
            "labelId": str(label_id), "sportType": sport_type, "limit": 1,
        })
        return parse_fit_url(text, label_id)

    def fitness_overview(self) -> CorosFitness:
        """The runner's current fitness assessment (R8.4.1). Read-only, no arguments."""
        return parse_fitness_overview(self._call_tool("queryFitnessAssessmentOverview", {}))

    def fetch_run(self, run: CorosRun) -> CorosRun:
        """Return `run` with its detail attached."""
        return merge_detail(run, self.get_run_detail(run.label_id, run.sport_type))

    # -- internals --------------------------------------------------------

    def _call_tool(self, name: str, arguments: dict) -> str:
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": "tools/call",
                   "params": {"name": name, "arguments": arguments}}
        body = self._request(payload)

        if "error" in body:
            err = body["error"] or {}
            msg = f"{name}: {err.get('message')} ({err.get('data')})"
            if err.get("code") in (-32601, -32602):
                # Tool renamed/removed or its arguments changed — the README warns this evolves.
                raise CorosContractError(f"COROS tool contract changed: {msg}")
            raise CorosApiError(msg)
        result = body.get("result") or {}
        content = result.get("content")
        if not isinstance(content, list) or not content or "text" not in content[0]:
            raise CorosContractError(f"{name}: response has no text content")
        text = content[0]["text"]
        if result.get("isError"):
            raise CorosApiError(f"{name}: {_unwrap_text(text)[:200]}")
        return text

    def _request(self, payload: dict) -> dict:
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                self._sleep(BACKOFF_S[min(attempt - 1, len(BACKOFF_S) - 1)])
            try:
                resp = self._post(
                    self._url,
                    headers={
                        "Authorization": f"Bearer {self._token()}",
                        "Accept": "application/json, text/event-stream",
                        "Content-Type": "application/json",
                        "MCP-Protocol-Version": "2025-06-18",
                    },
                    json=payload,
                    timeout=HTTP_TIMEOUT_S,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                logger.warning("COROS request failed (%s), attempt %d/%d", type(exc).__name__, attempt + 1, MAX_ATTEMPTS)
                continue
            if resp.status_code == 401:
                raise CorosAuthError("COROS rejected the access token (401)")
            if resp.status_code >= 500:
                last_exc = requests.HTTPError(f"COROS HTTP {resp.status_code}")
                logger.warning("COROS HTTP %d, attempt %d/%d", resp.status_code, attempt + 1, MAX_ATTEMPTS)
                continue
            if resp.status_code >= 400:
                raise CorosApiError(f"COROS HTTP {resp.status_code}")  # 4xx: never retried
            return self._decode(resp)
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _decode(resp: requests.Response) -> dict:
        raw = resp.text
        if "text/event-stream" in (resp.headers.get("content-type") or ""):
            data = next((ln[5:].strip() for ln in raw.splitlines() if ln.startswith("data:")), "")
            raw = data
        try:
            body = json.loads(raw)
        except ValueError:
            raise CorosContractError("COROS returned a non-JSON response")
        if not isinstance(body, dict):
            raise CorosContractError("COROS returned an unexpected JSON shape")
        return body
