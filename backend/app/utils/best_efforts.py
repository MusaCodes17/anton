"""Best efforts inside a run (R8.2) — pure functions, no app imports.

A run's per-second stream is a list of (elapsed_s, distance_m) samples. The
best effort for a target distance is the fastest stretch of the stream that
covers it, end to end, on the elapsed clock (stops inside the stretch count),
as Strava, COROS and Garmin define it. Validated against known races in the
R8.2 spike (Longueuil 10k: 10k 34:28, 5k 16:58); decision: design_decisions B19.

Streams come from FIT files (the watch's own cumulative distance — preferred)
or GPX (distance summed from GPS points; noisier). Raw files are never kept:
callers parse, compute, and store only the efforts. The one other thing read is
the run's start point (the first GPS fix, `fit_start` / `gpx_start`), which the
scan stores rounded to ~100 m (R5.4.1, utils/location.py) — never a track.
"""
from __future__ import annotations

import gzip
import io
import warnings
from typing import BinaryIO, Optional

# (label, metres) — the distances best efforts cover (runner's choice, R8.2).
EFFORT_DISTANCES: tuple[tuple[str, float], ...] = (
    ("1k", 1000.0),
    ("mile", 1609.344),
    ("5k", 5000.0),
    ("10k", 10000.0),
    ("half", 21097.5),
    ("full", 42195.0),
)

# GPX only: a step faster than this between two samples is a GPS jump, not
# running (8 m/s = 2:05/km, beyond any sustained human pace). Heuristic: the
# spike's one bad archive run was a GPX jump that faked a "1k in 0:02". FIT
# distance is the watch's own (already smoothed) — filtering it trimmed real
# distance and cost 2 s on a known 10k, so FIT only gets the monotonic fix.
MAX_STEP_SPEED_M_S = 8.0

Stream = list[tuple[float, float]]  # [(elapsed_s, distance_m)], both non-decreasing


def fit_stream(data: bytes) -> Stream:
    """Parse FIT bytes (optionally gzipped) into a stream from `record` messages."""
    import fitdecode

    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    out: Stream = []
    t0 = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # fitdecode warns on harmless odd field sizes
        with fitdecode.FitReader(io.BytesIO(data)) as reader:
            for frame in reader:
                if frame.frame_type != fitdecode.FIT_FRAME_DATA or frame.name != "record":
                    continue
                if not (frame.has_field("timestamp") and frame.has_field("distance")):
                    continue
                ts, dist = frame.get_value("timestamp"), frame.get_value("distance")
                if ts is None or dist is None:
                    continue
                t0 = t0 or ts
                out.append(((ts - t0).total_seconds(), float(dist)))
    return out


SEMICIRCLE_TO_DEG = 180.0 / 2 ** 31


def fit_start(data: bytes) -> Optional[tuple[float, float]]:
    """(lat, lon) in degrees of the first `record` with a valid GPS fix, or None.
    Full precision: rounding for storage is the caller's job (utils/location).

    FIT stores positions as semicircles (sint32). The default fitdecode reader
    returns those raw ints and does not convert them; a `StandardUnitsDataProcessor`
    reader returns degrees as floats. Both are handled: a float already within
    ±180 is taken as degrees, anything else as semicircles. Semicircle ints are
    never small in practice (a Montreal fix is ~5.4e8 / -8.8e8 semicircles), so
    this split is unambiguous for real files.
    """
    import fitdecode

    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with fitdecode.FitReader(io.BytesIO(data)) as reader:
            for frame in reader:
                if frame.frame_type != fitdecode.FIT_FRAME_DATA or frame.name != "record":
                    continue
                if not (frame.has_field("position_lat") and frame.has_field("position_long")):
                    continue
                lat, lon = frame.get_value("position_lat"), frame.get_value("position_long")
                if lat is None or lon is None:
                    continue
                return (_fit_degrees(lat), _fit_degrees(lon))
    return None


def _fit_degrees(value) -> float:
    if isinstance(value, float) and abs(value) <= 180.0:
        return float(value)          # already degrees (StandardUnitsDataProcessor)
    return float(value) * SEMICIRCLE_TO_DEG


def gpx_start(text: str) -> Optional[tuple[float, float]]:
    """(lat, lon) of the first track point in a GPX document, or None."""
    import gpxpy

    g = gpxpy.parse(text)
    for t in g.tracks:
        for s in t.segments:
            for p in s.points:
                return (p.latitude, p.longitude)
    return None


def gpx_stream(fh: BinaryIO | str) -> Stream:
    """Parse GPX into a stream, summing 2-D distance between timed points."""
    import gpxpy

    text = fh if isinstance(fh, str) else fh.read().decode("utf-8", "replace")
    g = gpxpy.parse(text)
    pts = [p for t in g.tracks for s in t.segments for p in s.points if p.time]
    out: Stream = []
    dist = 0.0
    for i, p in enumerate(pts):
        if i:
            dist += p.distance_2d(pts[i - 1]) or 0.0
        out.append(((p.time - pts[0].time).total_seconds(), dist))
    return out


def clean_stream(stream: Stream, *, max_step_speed_m_s: Optional[float] = None) -> Stream:
    """Force distance to be non-decreasing (a backwards step is held flat), and
    when `max_step_speed_m_s` is set, drop GPS jumps: a step faster than that has
    its distance gain removed (time still passes)."""
    if not stream:
        return []
    out: Stream = [stream[0]]
    shift = 0.0  # total distance removed so far
    for t, d in stream[1:]:
        pt, pd = out[-1]
        d -= shift
        step = d - pd
        dt = t - pt
        if step < 0:
            shift += step   # distance went backwards: hold it flat
            d = pd
        elif max_step_speed_m_s is not None and (dt <= 0 or step / dt > max_step_speed_m_s):
            shift += step   # a jump: keep the time, drop the distance
            d = pd
        out.append((t, d))
    return out


def best_effort_s(stream: Stream, target_m: float) -> Optional[tuple[float, float]]:
    """Fastest elapsed seconds to cover `target_m` anywhere in the stream, and
    the distance (m) at which that stretch starts. None if the run is shorter.

    Two pointers over the samples; the end point is interpolated to exactly
    `target_m`, so 1 s sampling doesn't round efforts up. O(n).
    """
    n = len(stream)
    best: Optional[tuple[float, float]] = None
    j = 0
    for i in range(n):
        t_i, d_i = stream[i]
        while j < n and stream[j][1] - d_i < target_m:
            j += 1
        if j >= n:
            break
        (t_a, d_a), (t_b, d_b) = stream[j - 1], stream[j]
        frac = (d_i + target_m - d_a) / (d_b - d_a) if d_b > d_a else 0.0
        dur = (t_a + frac * (t_b - t_a)) - t_i
        if best is None or dur < best[0]:
            best = (dur, d_i)
    return best


def best_efforts(stream: Stream, *, source: str = "fit") -> dict[str, tuple[int, int]]:
    """{label: (elapsed_s, start_offset_m)} for every EFFORT_DISTANCES entry the
    cleaned stream covers. `source` is "fit" or "gpx" (GPX gets the jump filter).
    Rounded to whole seconds / metres for storage."""
    cleaned = clean_stream(stream, max_step_speed_m_s=MAX_STEP_SPEED_M_S if source == "gpx" else None)
    out = {}
    for label, metres in EFFORT_DISTANCES:
        found = best_effort_s(cleaned, metres)
        if found is not None:
            out[label] = (round(found[0]), round(found[1]))
    return out
