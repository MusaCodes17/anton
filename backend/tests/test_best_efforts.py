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


# ── Start location (R5.4.1): the first GPS fix ───────────────────────────────

_FIT_CRC_TABLE = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
                  0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]


def _fit_crc(data: bytes, crc: int = 0) -> int:
    for b in data:
        for nibble in (b & 0xF, (b >> 4) & 0xF):
            tmp = _FIT_CRC_TABLE[crc & 0xF]
            crc = ((crc >> 4) & 0x0FFF) ^ tmp ^ _FIT_CRC_TABLE[nibble]
    return crc


def semicircles(deg: float) -> int:
    """FIT's sint32 position encoding."""
    return round(deg * 2 ** 31 / 180)


def fit_bytes(records, *, enhanced_alt: bool = False) -> bytes:
    """A minimal valid FIT file: one `record` definition, then one data message per
    record. Each record is (fit_timestamp_s, lat_semicircles | None, lon_semicircles | None,
    distance_m), optionally followed by heart_rate_bpm | None and altitude_m | None
    (every record must then have all six). None positions are written as the FIT invalid
    value (0x7FFFFFFF), None hr as 0xFF, None altitude as 0xFFFF (0xFFFFFFFF when
    `enhanced_alt` writes field 78, enhanced_altitude, instead of field 2, altitude).
    Altitude is encoded (m + 500) * 5, as the FIT profile does."""
    import struct
    with_extra = len(records[0]) == 6 if records else False
    fields = [(253, 4, 0x86), (0, 4, 0x85), (1, 4, 0x85), (5, 4, 0x86)]  # timestamp, lat, lon, distance
    fmt = "<IiiI"
    if with_extra:
        fields.append((3, 1, 0x02))                                        # heart_rate, uint8
        fields.append((78, 4, 0x86) if enhanced_alt else (2, 2, 0x84))     # enhanced_altitude u32 / altitude u16
        fmt += "B" + ("I" if enhanced_alt else "H")
    body = struct.pack("<BBBHB", 0x40, 0, 0, 20, len(fields))            # definition, record (20)
    body += b"".join(struct.pack("<BBB", n, size, base) for n, size, base in fields)
    invalid = 0x7FFFFFFF
    for rec in records:
        ts, lat, lon, dist = rec[:4]
        values = [
            ts,
            invalid if lat is None else lat,
            invalid if lon is None else lon,
            int(dist * 100),                                              # distance scale 100
        ]
        if with_extra:
            hr, alt = rec[4], rec[5]
            values.append(0xFF if hr is None else hr)
            if alt is None:
                values.append(0xFFFFFFFF if enhanced_alt else 0xFFFF)
            else:
                values.append(round((alt + 500) * 5))
        body += b"\x00" + struct.pack(fmt, *values)
    header = struct.pack("<BBHI", 14, 0x10, 2100, len(body)) + b".FIT"
    header += struct.pack("<H", _fit_crc(header))
    return header + body + struct.pack("<H", _fit_crc(body))


_MONTREAL = (45.501689, -73.576)
T0 = 1_000_000_000  # FIT epoch seconds (1989-12-31); a 2020s file. Tiny values come back as ints


def test_fit_start_converts_semicircles_to_degrees_and_skips_fixless_records():
    import gzip
    lat, lon = semicircles(_MONTREAL[0]), semicircles(_MONTREAL[1])
    data = fit_bytes([
        (T0, None, None, 0.0),        # no fix yet: skipped
        (T0 + 1, lat, lon, 1.0),      # first valid fix
        (T0 + 2, semicircles(45.6), semicircles(-73.5), 5.0),
    ])
    stream = be.fit_stream(data)     # the builder yields a file the real parser accepts
    assert stream[-1][1] == pytest.approx(5.0)
    start = be.fit_start(data)
    assert start == pytest.approx(_MONTREAL, abs=1e-6)   # semicircle resolution is ~1e-7 deg
    assert be.fit_start(gzip.compress(data)) == pytest.approx(_MONTREAL, abs=1e-6)


def test_fit_start_is_none_without_position_data():
    assert be.fit_start(fit_bytes([(T0, None, None, 0.0), (T0 + 1, None, None, 3.0)])) is None


def test_fit_degrees_passes_through_floats_already_in_degrees():
    # fitdecode's StandardUnitsDataProcessor hands back degrees as floats; the raw
    # reader hands back semicircle ints. Both must land on the same degrees.
    assert be._fit_degrees(_MONTREAL[0]) == _MONTREAL[0]
    assert be._fit_degrees(semicircles(_MONTREAL[0])) == pytest.approx(_MONTREAL[0], abs=1e-6)


def test_gpx_start_is_the_first_track_point():
    gpx = """<?xml version="1.0"?>
<gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
<trkpt lat="45.501689" lon="-73.576000"><time>2020-01-01T10:00:00Z</time></trkpt>
<trkpt lat="45.510000" lon="-73.570000"><time>2020-01-01T10:00:30Z</time></trkpt>
</trkseg></trk></gpx>"""
    assert be.gpx_start(gpx) == (45.501689, -73.576)


def test_gpx_start_is_none_without_points():
    assert be.gpx_start('<?xml version="1.0"?><gpx version="1.1" creator="t" '
                        'xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg></trkseg></trk></gpx>') is None


# --- per-km splits (R5.4.3) -------------------------------------------------

def _flat(t_from, d, seconds):
    """A standing stop: distance flat while the clock runs (1 Hz)."""
    return [(t_from + s, d) for s in range(1, seconds + 1)]


def _constant_2500():
    return [(float(s), 4.0 * s) for s in range(0, 626)]   # 4 m/s for 2500 m


def test_splits_constant_pace():
    sp = be.km_splits(_constant_2500())
    assert [(s.index, s.distance_m, s.elapsed_s, s.moving_s) for s in sp] == [
        (1, 1000, 250, 250), (2, 1000, 250, 250), (3, 500, 125, 125)]


def test_splits_interpolate_a_boundary_inside_an_interval():
    # 10 s samples at 4:05/km: km 1 ends at t=245, inside the 240-250 s interval.
    stream = [(t, t * 1000 / 245) for t in range(0, 500, 10)]
    sp = be.km_splits(stream)
    assert sp[0].distance_m == 1000
    assert sp[0].elapsed_s == 245 and sp[0].moving_s == 245
    assert sp[1].elapsed_s == 245


def test_splits_stop_adds_elapsed_not_moving():
    a = [(float(s), 4.0 * s) for s in range(0, 376)]            # 1500 m, in km 2
    stop = _flat(a[-1][0], a[-1][1], 120)
    b = [(stop[-1][0] + s, 1500 + 4.0 * s) for s in range(1, 376)]  # to 3000 m
    sp = be.km_splits(a + stop + b)
    assert sp[0].elapsed_s == sp[0].moving_s == 250
    assert sp[1].elapsed_s == 370 and sp[1].moving_s == 250
    assert sp[2].elapsed_s == sp[2].moving_s == 250


def test_splits_auto_pause_gap_counts_as_stopped():
    a = [(float(s), 4.0 * s) for s in range(0, 126)]            # 500 m
    gap = (a[-1][0] + 300, a[-1][1] + 3)                         # 300 s covering 3 m
    b = [(gap[0] + s, gap[1] + 4.0 * s) for s in range(1, 251)]
    sp = be.km_splits(a + [gap] + b)
    assert sp[0].elapsed_s - sp[0].moving_s == pytest.approx(300, abs=2)


def test_splits_trailing_partial_threshold():
    short = [(float(s), 4.0 * s) for s in range(0, 261)]        # 1040 m
    assert [s.distance_m for s in be.km_splits(short)] == [1000]
    kept = [(float(s), 4.0 * s) for s in range(0, 264)]         # 1052 m
    sp = be.km_splits(kept)
    assert [s.distance_m for s in sp] == [1000, 52]


def test_splits_empty_and_single_sample():
    assert be.km_splits([]) == []
    assert be.km_splits([(0.0, 0.0)]) == []


def test_splits_gpx_jump_filter_adds_no_kilometres():
    run = [(0.0, 0.0)] + _steady(360, 1.5)                      # 1500 m
    i = len(run) // 2
    jumped = run[:i] + [(t, d + 3000) for t, d in run[i:]]
    assert len(be.km_splits(jumped, source="gpx")) == 2         # 1000 + ~500, not 4+
    assert len(be.km_splits(jumped, source="fit")) > 2          # FIT trusted as recorded


def test_splits_elapsed_sums_to_duration():
    stream = _constant_2500()
    stream = stream[:300] + [(t + 37, d) for t, d in stream[300:]]  # one 37 s gap
    sp = be.km_splits(stream)
    assert abs(sum(s.elapsed_s for s in sp) - stream[-1][0]) <= len(sp)


# --- per-km heart rate and elevation (R5.4.3) ---------------------------------

def test_splits_without_hr_or_alt_have_none_fields():
    sp = be.km_splits(_constant_2500())
    assert all(s.avg_hr is None and s.elev_gain_m is None and s.elev_loss_m is None for s in sp)


def test_splits_avg_hr_excludes_a_stop():
    # km 1: 250 s moving at 150 bpm. km 2: 125 s moving at 150, a 120 s stop where HR
    # falls to 90, then 125 s moving at 150. A time-weighted average over the stop
    # would pull km 2 below 150; the moving-time weight keeps it exactly 150.
    a = [(float(s), 4.0 * s) for s in range(0, 376)]
    stop = _flat(a[-1][0], a[-1][1], 120)
    b = [(stop[-1][0] + s, 1500 + 4.0 * s) for s in range(1, 376)]
    stream = a + stop + b
    hr = [150.0] * len(a) + [90.0] * len(stop) + [150.0] * len(b)
    sp = be.km_splits(stream, hr=hr)
    assert sp[0].avg_hr == 150
    assert sp[1].elapsed_s == 370 and sp[1].avg_hr == 150


def test_splits_avg_hr_weights_by_moving_time_and_uses_endpoint_mean():
    stream = _constant_2500()
    hr = [140.0] * 126 + [160.0] * 500
    sp = be.km_splits(stream, hr=hr)
    # km 1 has 250 one-second intervals: 125 at 140, one straddling the change (mean
    # of its endpoints, 150), and 124 at 160.
    assert sp[0].avg_hr == round((140 * 125 + 150 * 1 + 160 * 124) / 250)
    assert sp[2].avg_hr == 160


def test_splits_hr_missing_endpoints_and_all_missing():
    stream = _constant_2500()
    hr = [None] * len(stream)
    hr[10] = 155.0                              # one sample: its two intervals use that one value
    assert be.km_splits(stream, hr=hr)[0].avg_hr == 155
    assert be.km_splits(stream, hr=[None] * len(stream))[0].avg_hr is None
    assert be.km_splits(stream, hr=hr)[1].avg_hr is None   # no HR-bearing moving time in km 2


def test_splits_elevation_gain_and_loss_across_a_boundary():
    # 1 Hz at 4 m/s (a km every 250 s). Altitude climbs 0.125 m/s for 300 s (37.5 m),
    # then falls 0.25 m/s. Both are exact in binary, so the 2 m hysteresis steps land
    # on whole samples: the counted level moves every 16 s up and every 8 s down.
    stream = _constant_2500()
    alt = []
    a = 100.0
    for i in range(len(stream)):
        alt.append(a)
        a += 0.125 if i < 300 else -0.25
    sp = be.km_splits(stream, alt=alt)
    # km 1 (t 0-250): the level steps up 15 times (t=16..240) = 30 m. km 2 (t 250-500):
    # 3 more steps up to t=288 (6 m: the level was already 30, peak 36), then 24 steps down (36 to -12) = 48 m.
    assert (sp[0].elev_gain_m, sp[0].elev_loss_m) == (30.0, 0.0)
    assert sp[1].elev_gain_m == pytest.approx(6.0, abs=0.1)
    assert sp[1].elev_loss_m == pytest.approx(48.0, abs=0.1)


def test_splits_elevation_jitter_below_the_hysteresis_counts_for_nothing():
    stream = _constant_2500()
    alt = [100.0 + (i % 2) for i in range(len(stream))]       # 1 m up/down every second
    assert be.ELEV_HYSTERESIS_M > 1.0
    for s in be.km_splits(stream, alt=alt):
        assert (s.elev_gain_m, s.elev_loss_m) == (0.0, 0.0)   # present but zero, not None


def test_splits_elevation_real_climb_in_small_steps_is_counted():
    stream = [(float(s), 4.0 * s) for s in range(21)]         # 80 m: one partial split
    alt = [0.5 * i for i in range(21)]                        # a 10 m climb in 0.5 m steps
    sp = be.km_splits(stream, alt=alt)
    assert sp[0].elev_gain_m == pytest.approx(10.0, abs=0.1)
    assert sp[0].elev_loss_m == 0.0


def test_splits_elevation_interval_delta_is_split_across_the_boundary():
    # The 245 s -> 255 s interval covers 980-1020 m at 4 m/s, so the km boundary falls in
    # its middle; its 10 m climb is divided in proportion to the distance on each side.
    stream = [(0.0, 0.0), (245.0, 980.0), (255.0, 1020.0), (500.0, 2000.0)]
    alt = [0.0, 0.0, 10.0, 10.0]
    sp = be.km_splits(stream, alt=alt)
    assert sp[0].elev_gain_m == pytest.approx(5.0, abs=0.1)    # 20/40 of the 10 m
    assert sp[1].elev_gain_m == pytest.approx(5.0, abs=0.1)


def test_splits_missing_altitude_gives_none_and_gaps_skip_the_interval():
    stream = _constant_2500()
    assert be.km_splits(stream, alt=[None] * len(stream))[0].elev_gain_m is None
    alt = [3.0 * (i % 2) for i in range(len(stream))]  # 0, 3, 0, 3, ...: +3 then -3 per interval
    alt[5] = None                                      # the two intervals touching it have no delta
    sp = be.km_splits(stream, alt=alt)
    assert (sp[0].elev_gain_m, sp[0].elev_loss_m) == (372.0, 372.0)   # 124 each of 3 m (125, minus one of each)


def test_splits_length_mismatch_is_an_error():
    stream = _constant_2500()
    with pytest.raises(ValueError):
        be.km_splits(stream, hr=[150.0] * (len(stream) - 1))
    with pytest.raises(ValueError):
        be.km_splits(stream, alt=[0.0])


def test_clean_stream_keeps_one_sample_per_input():
    stream = [(0, 0), (2, 10), (4, 8), (6, 18), (7, 5000)]
    assert len(be.clean_stream(stream)) == len(stream)
    assert len(be.clean_stream(stream, max_step_speed_m_s=8.0)) == len(stream)


def test_fit_records_reads_hr_and_altitude_aligned_with_the_stream():
    import gzip
    recs = [(T0 + s, None, None, s * 3.0, None if s == 2 else 140 + s, None if s == 3 else 10.0 + s) for s in range(0, 5)]
    stream, hr, alt = be.fit_records(gzip.compress(fit_bytes(recs)))
    assert stream == be.fit_stream(fit_bytes(recs))
    assert hr == [140.0, 141.0, None, 143.0, 144.0]
    assert alt == [10.0, 11.0, 12.0, None, 14.0]          # whole metres are exact in FIT's 0.2 m steps


def test_fit_records_prefers_enhanced_altitude_and_none_without_the_fields():
    recs = [(T0 + s, None, None, s * 3.0, 150, 20.0 + s) for s in range(0, 3)]
    _, _, alt = be.fit_records(fit_bytes(recs, enhanced_alt=True))
    assert alt == pytest.approx([20.0, 21.0, 22.0], abs=0.2)
    plain = be.fit_records(fit_bytes([(T0 + s, None, None, s * 3.0) for s in range(3)]))
    assert plain[1] == [None] * 3 and plain[2] == [None] * 3


def test_gpx_records_reads_tpx_hr_and_ele():
    gpx = """<?xml version="1.0"?>
<gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1"
 xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"><trk><trkseg>
<trkpt lat="45.5000" lon="-73.6000"><ele>30.5</ele><time>2020-01-01T10:00:00Z</time>
 <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>148</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>
<trkpt lat="45.5009" lon="-73.6000"><time>2020-01-01T10:00:30Z</time></trkpt>
<trkpt lat="45.5018" lon="-73.6000"><ele>32</ele><time>2020-01-01T10:01:00Z</time>
 <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>152</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>
</trkseg></trk></gpx>"""
    stream, hr, alt = be.gpx_records(gpx)
    assert stream == be.gpx_stream(gpx) and len(stream) == 3
    assert hr == [148.0, None, 152.0]
    assert alt == [30.5, None, 32.0]
