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
The same cleaned stream also yields per-km splits (`km_splits`, R5.4.3), with
average heart rate and elevation gain/loss when the file carries them
(`fit_records` / `gpx_records` return those channels aligned with the stream).
"""
from __future__ import annotations

import gzip
import io
import warnings
from dataclasses import dataclass
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

SPLIT_M = 1000.0  # per-km splits (R5.4.3)
# Heuristic: a sample interval slower than this (≈33:20/km) is standing still or an
# auto-pause gap, so it counts toward elapsed but not moving time.
STOP_SPEED_M_S = 0.5
# A trailing partial km shorter than this is GPS noise at the stop button and is dropped.
MIN_LAST_SPLIT_M = 50.0


Records = tuple[Stream, list[Optional[float]], list[Optional[float]]]  # (stream, hr_bpm, alt_m)


def fit_stream(data: bytes) -> Stream:
    """Parse FIT bytes (optionally gzipped) into a stream from `record` messages."""
    return fit_records(data)[0]


def fit_records(data: bytes) -> Records:
    """Parse FIT bytes (optionally gzipped) into (stream, hr, alt). `hr` (bpm,
    from `heart_rate`) and `alt` (m, from `enhanced_altitude`, else `altitude`)
    are aligned index-for-index with the stream's samples; None where the record
    has no value. The stream is every `record` frame with a timestamp and distance."""
    import fitdecode

    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    out: Stream = []
    hr: list[Optional[float]] = []
    alt: list[Optional[float]] = []
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
                hr.append(_fit_number(frame, "heart_rate"))
                a = _fit_number(frame, "enhanced_altitude")
                alt.append(a if a is not None else _fit_number(frame, "altitude"))
    return out, hr, alt


def _fit_number(frame, name: str) -> Optional[float]:
    if not frame.has_field(name):
        return None
    value = frame.get_value(name)
    return None if value is None else float(value)


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
    return gpx_records(fh)[0]


def gpx_records(fh: BinaryIO | str) -> Records:
    """Parse GPX into (stream, hr, alt), summing 2-D distance between timed points.
    `hr` comes from the point's TrackPointExtension (any extension descendant whose
    tag ends with "hr", e.g. gpxtpx:hr); `alt` is the point's `<ele>`. Both are
    aligned with the stream's samples, None where absent."""
    import gpxpy

    text = fh if isinstance(fh, str) else fh.read().decode("utf-8", "replace")
    g = gpxpy.parse(text)
    pts = [p for t in g.tracks for s in t.segments for p in s.points if p.time]
    out: Stream = []
    hr: list[Optional[float]] = []
    alt: list[Optional[float]] = []
    dist = 0.0
    for i, p in enumerate(pts):
        if i:
            dist += p.distance_2d(pts[i - 1]) or 0.0
        out.append(((p.time - pts[0].time).total_seconds(), dist))
        hr.append(_gpx_hr(p))
        alt.append(None if p.elevation is None else float(p.elevation))
    return out, hr, alt


def _gpx_hr(point) -> Optional[float]:
    for ext in point.extensions or []:
        for el in ext.iter():
            if isinstance(el.tag, str) and el.tag.endswith("hr") and el.text:
                try:
                    return float(el.text)
                except ValueError:
                    return None
    return None


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


@dataclass(frozen=True)
class Split:
    """One kilometre (or the trailing partial) of a run. `index` is 1-based;
    `distance_m` is 1000 for full splits, the remainder for the last partial.
    `avg_hr` (bpm) is weighted by moving time; `elev_gain_m` / `elev_loss_m` are
    the climb and descent in metres. Each is None when the file had no data for
    that split."""

    index: int
    distance_m: int
    elapsed_s: int
    moving_s: int
    avg_hr: Optional[int] = None
    elev_gain_m: Optional[float] = None
    elev_loss_m: Optional[float] = None


# An altitude change counts only once it moves at least this far from the last counted
# level; this suppresses barometric and GPS jitter. Tuned on 40 archive runs against
# Strava's elevation gain (2 m gives a median of 0.92x, raw sums 1.29x). Heuristic.
ELEV_HYSTERESIS_M = 2.0


def km_splits(stream: Stream, *, source: str = "fit",
              hr: Optional[list[Optional[float]]] = None,
              alt: Optional[list[Optional[float]]] = None) -> list[Split]:
    """Per-km splits of the cleaned stream (same cleaning as `best_efforts`: the
    jump filter applies to GPX only). Boundaries fall every SPLIT_M metres of
    cleaned distance from the first sample; an interval that crosses one has its
    time divided in proportion to the distance on each side (linear interpolation).

    `elapsed_s` is wall-clock time in the split, so the sum across splits equals
    the stream duration up to per-split rounding. `moving_s` excludes intervals
    slower than STOP_SPEED_M_S — a heuristic that treats standing stops and
    auto-pause gaps as not moving. A trailing partial km is kept only if it is at
    least MIN_LAST_SPLIT_M. Empty or single-sample streams give [].

    `hr` (bpm) and `alt` (m), when given, are lists aligned index-for-index with
    `stream` (ValueError if the lengths differ; `clean_stream` keeps one sample per
    input so alignment survives cleaning). Altitude is first stepped through an
    ELEV_HYSTERESIS_M threshold (a sample only moves the counted level once it is at
    least that far from it; None samples stay None), so gain and loss are hysteresis
    sums, not raw ones. An interval's heart rate is the mean of
    its two endpoints, or the one present; `avg_hr` weights it by the interval's
    moving time only, because heart rate falls during stops, and is None when the
    split has no moving time with heart rate. An interval's altitude change
    (alt1 - alt0, needs both) is divided across a km boundary like time; gain sums
    the climbs and loss the descents, None when no interval had both altitudes.
    """
    for name, channel in (("hr", hr), ("alt", alt)):
        if channel is not None and len(channel) != len(stream):
            raise ValueError(f"{name} has {len(channel)} samples but the stream has {len(stream)}")
    if alt is not None:
        alt = _hysteresis(alt)
    cleaned = clean_stream(stream, max_step_speed_m_s=MAX_STEP_SPEED_M_S if source == "gpx" else None)
    out: list[Split] = []
    acc_d = acc_t = acc_mv = 0.0   # the split being accumulated
    hr_w = hr_t = 0.0              # Σ hr × moving seconds, Σ moving seconds with hr
    gain = loss = 0.0
    has_alt = False

    def emit(dist: float) -> None:
        out.append(Split(
            len(out) + 1, round(dist), round(acc_t), round(acc_mv),
            avg_hr=round(hr_w / hr_t) if hr_t > 0 else None,
            elev_gain_m=round(gain, 1) if has_alt else None,
            elev_loss_m=round(loss, 1) if has_alt else None,
        ))

    for i in range(len(cleaned) - 1):
        (t0, d0), (t1, d1) = cleaned[i], cleaned[i + 1]
        dt, dd = t1 - t0, d1 - d0
        mv = dt if (dt > 0 and dd / dt >= STOP_SPEED_M_S) else 0.0
        hv = _mean_present(hr[i], hr[i + 1]) if hr is not None else None
        dh = alt[i + 1] - alt[i] if alt is not None and alt[i] is not None and alt[i + 1] is not None else None

        def take(frac: float) -> None:
            """Assign `frac` of this interval's time, moving time and altitude change to the split."""
            nonlocal acc_t, acc_mv, hr_w, hr_t, gain, loss, has_alt
            acc_t += dt * frac
            acc_mv += mv * frac
            if hv is not None and mv > 0:
                hr_w += hv * mv * frac
                hr_t += mv * frac
            if dh is not None:
                has_alt = True
                gain += max(dh, 0.0) * frac
                loss += max(-dh, 0.0) * frac

        if dd <= 0:
            take(1.0)            # flat distance: wholly in the current split
            continue
        left = dd                # distance of this interval not yet assigned
        while acc_d + left >= SPLIT_M:
            need = SPLIT_M - acc_d
            take(need / dd)
            emit(SPLIT_M)
            acc_d = acc_t = acc_mv = 0.0
            hr_w = hr_t = gain = loss = 0.0
            has_alt = False
            left -= need
        take(left / dd)
        acc_d += left
    if acc_d >= MIN_LAST_SPLIT_M:
        emit(acc_d)
    return out


def _hysteresis(alt: list[Optional[float]]) -> list[Optional[float]]:
    """Stepped altitude: the counted level moves to a sample only when that sample is
    at least ELEV_HYSTERESIS_M away from it. None where the input is None (the level
    carries across gaps), so the result stays aligned with the input."""
    ref: Optional[float] = None
    out: list[Optional[float]] = []
    for a in alt:
        if a is None:
            out.append(None)
            continue
        if ref is None or abs(a - ref) >= ELEV_HYSTERESIS_M:
            ref = a
        out.append(ref)
    return out


def _mean_present(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is not None and b is not None:
        return (a + b) / 2
    return a if a is not None else b
