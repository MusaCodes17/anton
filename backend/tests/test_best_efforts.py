"""
Best efforts inside a run (R8.2) — the pure engine in app/utils/best_efforts.

The rules: the fastest stretch covering a distance is found anywhere in the
run (a 5k inside a 10k), timed on the elapsed clock (a stop inside the stretch
counts), interpolated to the exact distance, and GPS jumps don't fake records.
Streams are synthetic: real FIT/GPX files carry the runner's GPS track, so the
engine was validated against real races in the spike instead
(R8.2 spike: Longueuil 10k → 10k 34:28, 5k 16:58).
"""
import pytest

from app.utils import best_efforts as be


def _steady(pace_s_per_km, km, start=(0.0, 0.0)):
    """1 Hz samples at a constant pace."""
    t0, d0 = start
    n = round(km * pace_s_per_km)          # seconds to cover km
    speed = km * 1000 / n
    return [(t0 + s, d0 + s * speed) for s in range(1, n + 1)]


def test_finds_the_fast_5k_inside_a_10k():
    # 5 km easy at 5:00/km, then 5 km hard at 3:20/km.
    easy = [(0.0, 0.0)] + _steady(300, 5)
    hard = _steady(200, 5, start=easy[-1])
    effort = be.best_efforts(easy + hard)
    assert effort["5k"][0] == pytest.approx(1000, abs=2)   # 5 km at 3:20/km
    assert effort["5k"][1] == pytest.approx(5000, abs=5)   # it starts where the hard half starts
    assert effort["10k"][0] == pytest.approx(2500, abs=2)  # the whole run
    assert "half" not in effort                            # shorter than 21.1 km


def test_a_stop_inside_the_stretch_counts():
    # 1k, a 60 s standing stop, another 1k: the 1k effort is one clean
    # kilometre, but any mile has to include the stop.
    a = [(0.0, 0.0)] + _steady(240, 1)
    stop_end = (a[-1][0] + 60, a[-1][1])
    b = _steady(240, 1, start=stop_end)
    effort = be.best_efforts(a + [stop_end] + b)
    assert effort["1k"][0] == pytest.approx(240, abs=2)
    assert effort["mile"][0] == pytest.approx(1609.344 * 0.24 + 60, abs=3)


def test_end_point_is_interpolated_not_rounded_to_a_sample():
    # 10 s samples at 4:00/km: 1000 m lands between samples.
    stream = [(t, t * 1000 / 240) for t in range(0, 400, 10)]
    assert be.best_effort_s(stream, 1000)[0] == pytest.approx(240, abs=0.01)


def test_gps_jump_does_not_fake_a_record():
    # A steady 6:00/km run with a 500 m teleport in one second.
    run = [(0.0, 0.0)] + _steady(360, 3)
    i = len(run) // 2
    jumped = run[:i] + [(t, d + 500) for t, d in run[i:]]
    effort = be.best_efforts(jumped, source="gpx")
    assert effort["1k"][0] == pytest.approx(360, abs=3)   # not ~4 minutes faster
    # FIT distance is the watch's own and is trusted as recorded.
    assert be.best_efforts(jumped, source="fit")["1k"][0] < 300


def test_distance_going_backwards_is_held_flat():
    stream = [(0, 0), (2, 10), (4, 8), (6, 18)]
    assert be.clean_stream(stream) == [(0, 0), (2, 10), (4, 10), (6, 20)]


def test_short_or_empty_runs_have_no_efforts():
    assert be.best_efforts([]) == {}
    assert be.best_efforts([(0.0, 0.0)] + _steady(300, 0.8)) == {}


def test_gpx_stream_sums_point_distance():
    gpx = """<?xml version="1.0"?>
<gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
<trkpt lat="45.5000" lon="-73.6000"><time>2020-01-01T10:00:00Z</time></trkpt>
<trkpt lat="45.5009" lon="-73.6000"><time>2020-01-01T10:00:30Z</time></trkpt>
<trkpt lat="45.5018" lon="-73.6000"><time>2020-01-01T10:01:00Z</time></trkpt>
</trkseg></trk></gpx>"""
    stream = be.gpx_stream(gpx)
    assert [t for t, _ in stream] == [0, 30, 60]
    assert stream[-1][1] == pytest.approx(200, abs=2)       # 0.0018° of latitude ≈ 200 m
