"""R8.2 spike S1 (throwaway, not app code): best efforts from FIT/GPX streams.

Needs `pip install fitdecode gpxpy` in a scratch venv. Usage:
    python scripts/spikes/best_efforts.py <export_dir> activities/<id>.fit.gz ...
Decision: docs/design_decisions.md B19.
"""
import gzip, math, sys, time
import fitdecode, gpxpy

TARGETS = {"1k": 1000, "5k": 5000, "10k": 10000, "half": 21097.5, "full": 42195}

def fit_stream(path):
    """[(t_s, dist_m)] from FIT record messages (device-recorded cumulative distance)."""
    out, t0 = [], None
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as fh, fitdecode.FitReader(fh) as fr:
        for frame in fr:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA or frame.name != "record":
                continue
            if not (frame.has_field("timestamp") and frame.has_field("distance")):
                continue
            ts, d = frame.get_value("timestamp"), frame.get_value("distance")
            if ts is None or d is None:
                continue
            t0 = t0 or ts
            out.append(((ts - t0).total_seconds(), float(d)))
    return out

def gpx_stream(path):
    """[(t_s, dist_m)] by summing haversine between GPS points (no device distance in GPX)."""
    with open(path) as fh:
        g = gpxpy.parse(fh)
    pts = [p for t in g.tracks for s in t.segments for p in s.points if p.time]
    out, dist = [], 0.0
    for i, p in enumerate(pts):
        if i:
            dist += p.distance_2d(pts[i - 1]) or 0.0
        out.append(((p.time - pts[0].time).total_seconds(), dist))
    return out

def best_effort(stream, target_m):
    """Fastest elapsed time to cover target_m anywhere in the stream (two pointers,
    interpolating the end point to exactly target_m). None if the run is shorter."""
    best, j = None, 0
    n = len(stream)
    for i in range(n):
        t_i, d_i = stream[i]
        while j < n and stream[j][1] - d_i < target_m:
            j += 1
        if j >= n:
            break
        (t_a, d_a), (t_b, d_b) = stream[j - 1], stream[j]
        frac = (d_i + target_m - d_a) / (d_b - d_a) if d_b > d_a else 0.0
        t_end = t_a + frac * (t_b - t_a)
        dur = t_end - t_i
        if best is None or dur < best:
            best = dur
    return best

def fmt(s):
    if s is None: return "—"
    s = round(s); h, r = divmod(s, 3600); m, sec = divmod(r, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

if __name__ == "__main__":
    base = sys.argv[1]
    for rel in sys.argv[2:]:
        p = f"{base}/{rel}"
        t = time.time()
        st = fit_stream(p) if ".fit" in rel else gpx_stream(p)
        dt = time.time() - t
        if not st:
            print(rel, "NO STREAM"); continue
        gaps = [b[0] - a[0] for a, b in zip(st, st[1:])]
        med = sorted(gaps)[len(gaps)//2] if gaps else None
        print(f"{rel}: {len(st)} pts, {st[-1][1]/1000:.2f} km, {fmt(st[-1][0])} elapsed, median gap {med}s, parse {dt:.2f}s")
        print("   ", "  ".join(f"{k} {fmt(best_effort(st, m))}" for k, m in TARGETS.items()))
