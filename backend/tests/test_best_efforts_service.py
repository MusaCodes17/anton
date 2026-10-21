"""
Best efforts storage and scanning (R8.2) — services/best_efforts, the COROS
FIT-URL contract, and the poll-tick hook.

The rules:
  - a scan replaces a run's efforts and is recorded, so settled runs are
    never re-scanned; failures retry up to MAX_SCAN_ATTEMPTS, then stop;
  - one bad file never stops a backfill;
  - the COROS FIT URL is parsed by an anchored contract and never stored or
    logged (it is an unsigned link to the run's GPS track);
  - the poll tick scans after polling, and a scan failure never fails the poll;
  - efforts die with their activity;
  - per-km splits (R5.4.3) are written by the same scan, replaced on rescan,
    die with the activity, and an ok scan below SCAN_VERSION is re-scanned once.
"""
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.models import (
    Activity, ActivityBestEffort, ActivityEffortScan, ActivitySplit, CorosConnection, OwnedShoe, ShoeRun,
)
from app.services import best_efforts as svc
from app.services import coros_poller as poller
from app.services.coros_mcp_client import CorosContractError, parse_fit_url
from tests.test_best_efforts import T0, fit_bytes, semicircles

FIX = Path(__file__).parent / "fixtures" / "coros" / "fit_download_urls.json"
URL_TEXT = json.loads(FIX.read_text())["result"]["content"][0]["text"]


def _gpx(km, pace_s_per_km=300):
    """A straight-north GPX track at a steady pace, one point every 10 s."""
    from datetime import datetime, timedelta
    t0 = datetime(2020, 1, 1, 10, 0, 0)
    step_m = 10 * 1000 / pace_s_per_km
    n = int(km * 1000 / step_m) + 1
    pts = "".join(
        f'<trkpt lat="{45.5 + i * step_m / 111_195:.7f}" lon="-73.6"><time>{(t0 + timedelta(seconds=10 * i)).isoformat()}Z</time></trkpt>'
        for i in range(n)
    )
    return f'<?xml version="1.0"?><gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>{pts}</trkseg></trk></gpx>'


def _run(db, *, source="strava", fit_filename=None, coros_id=None, d=date(2020, 1, 1), atype="Run"):
    a = Activity(source=source, activity_type=atype, run_date=d, distance_km=5.0,
                 fit_filename=fit_filename, coros_activity_id=coros_id)
    db.add(a)
    db.commit()
    return a


def _efforts(db, activity_id):
    return {e.distance_label: e.elapsed_s for e in
            db.query(ActivityBestEffort).filter(ActivityBestEffort.activity_id == activity_id)}


# ── The archive backfill ─────────────────────────────────────────────────────

def test_archive_scan_stores_efforts_and_skips_settled_runs(db, tmp_path):
    (tmp_path / "activities").mkdir()
    (tmp_path / "activities" / "1.gpx").write_text(_gpx(5.2))
    a = _run(db, fit_filename="activities/1.gpx")
    _run(db, fit_filename="activities/ride.gpx", atype="Ride")   # not a run: never scanned

    first = svc.scan_archive(db, tmp_path)
    assert (first.scanned, first.failed) == (1, 0)
    eff = _efforts(db, a.id)
    assert set(eff) == {"1k", "mile", "5k"}
    assert eff["5k"] == pytest.approx(1500, abs=2)            # 5:00/km
    assert db.get(ActivityEffortScan, a.id).status == "ok"

    again = svc.scan_archive(db, tmp_path)
    assert again.scanned == 0                                  # settled: not re-read


def test_bad_file_is_isolated_and_retried_a_bounded_number_of_times(db, tmp_path):
    (tmp_path / "activities").mkdir()
    (tmp_path / "activities" / "ok.gpx").write_text(_gpx(1.2))
    good = _run(db, fit_filename="activities/ok.gpx")
    missing = _run(db, fit_filename="activities/missing.fit.gz")

    s = svc.scan_archive(db, tmp_path)
    assert (s.scanned, s.failed) == (1, 1)
    assert _efforts(db, good.id)                              # the good run still landed
    for _ in range(5):
        svc.scan_archive(db, tmp_path)
    scan = db.get(ActivityEffortScan, missing.id)
    assert scan.status == "failed" and scan.attempts == svc.MAX_SCAN_ATTEMPTS


def test_rescan_replaces_rows(db, tmp_path):
    (tmp_path / "activities").mkdir()
    f = tmp_path / "activities" / "1.gpx"
    f.write_text(_gpx(1.2, pace_s_per_km=300))
    a = _run(db, fit_filename="activities/1.gpx")
    svc.scan_archive(db, tmp_path)
    f.write_text(_gpx(1.2, pace_s_per_km=240))
    svc.scan_archive(db, tmp_path, rescan=True)
    assert _efforts(db, a.id)["1k"] == pytest.approx(240, abs=2)
    assert db.query(ActivityBestEffort).filter(ActivityBestEffort.activity_id == a.id).count() == 1


def test_efforts_die_with_their_activity(db, tmp_path):
    db.execute(text("PRAGMA foreign_keys=ON"))               # production enables this per connection
    (tmp_path / "activities").mkdir()
    (tmp_path / "activities" / "1.gpx").write_text(_gpx(1.2))
    a = _run(db, fit_filename="activities/1.gpx")
    svc.scan_archive(db, tmp_path)
    db.delete(a)
    db.commit()
    assert db.query(ActivityBestEffort).count() == 0
    assert db.query(ActivityEffortScan).count() == 0


# ── COROS: the FIT URL contract and the scan ─────────────────────────────────

def test_fit_url_contract():
    url = parse_fit_url(URL_TEXT, "400000000000000001")
    assert url.startswith("https://s3.coros.com/fit/") and url.endswith("/400000000000000001.fit")
    with pytest.raises(CorosContractError) as e:
        parse_fit_url(URL_TEXT, "400000000000000999")        # another run's file is never taken
    assert "https://" not in str(e.value)                    # no URL in the error


class _Resp:
    def __init__(self, content=b"FIT", status=200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} for url https://s3.coros.com/fit/secret.fit")


class _Client:
    def __init__(self):
        self.asked = []

    def fit_url(self, label_id, sport_type=100):
        self.asked.append(label_id)
        return f"https://s3.coros.com/fit/u/{label_id}.fit"


def test_coros_scan_rations_downloads_and_never_stores_the_url(db, monkeypatch):
    stream = [(float(s), s * 1000 / 240) for s in range(0, 300)]   # 1.25 km at 4:00/km
    monkeypatch.setattr(svc.engine, "fit_records", lambda data: (stream, [None] * len(stream), [None] * len(stream)))
    for i in range(7):
        _run(db, source="coros", coros_id=f"L{i}", d=date(2026, 10, 1 + i))
    client = _Client()

    s = svc.scan_coros(db, client, limit=5, get=lambda url, timeout: _Resp())
    assert s.scanned == 5 and len(client.asked) == 5
    assert client.asked[0] == "L6"                           # newest first
    assert all(e == pytest.approx(240, abs=1) for e in
               [e.elapsed_s for e in db.query(ActivityBestEffort).filter_by(distance_label="1k")])

    failing = svc.scan_coros(db, client, limit=5, get=lambda url, timeout: _Resp(status=403))
    assert failing.failed == 2
    for scan in db.query(ActivityEffortScan).filter_by(status="failed"):
        assert "s3.coros.com" not in (scan.error or "")         # only the exception type is kept


def test_poll_tick_scans_after_polling_and_a_scan_failure_never_fails_the_poll(db, monkeypatch):
    db.add(CorosConnection(id=1, status="connected"))
    db.commit()
    _run(db, source="coros", coros_id="L1", d=date(2026, 10, 6))

    class Client(_Client):
        def list_runs(self, start, end):
            return []

        def fit_url(self, label_id, sport_type=100):
            raise RuntimeError("COROS down")

    result = poller.run_tick(db, client=Client(), today=date(2026, 10, 7))
    assert result.ok                                         # the poll itself succeeded
    assert db.query(ActivityEffortScan).one().status == "failed"


# ── Start location on archive scans (R5.4.1) ─────────────────────────────────

def _gpx_with_start(lat, lon, pace_s_per_km=300):
    """_gpx's track, but its first point is at (lat, lon)."""
    from datetime import datetime, timedelta
    t0 = datetime(2020, 1, 1, 10, 0, 0)
    pts = "".join(
        f'<trkpt lat="{lat + i * 0.0001:.6f}" lon="{lon}"><time>{(t0 + timedelta(seconds=10 * i)).isoformat()}Z</time></trkpt>'
        for i in range(400)  # ~4.4 km: long enough for a 1k effort
    )
    return f'<?xml version="1.0"?><gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>{pts}</trkseg></trk></gpx>'


def test_archive_scan_stamps_rounded_start_and_touches_nothing_else(db, tmp_path):
    (tmp_path / "activities").mkdir()
    (tmp_path / "activities" / "1.gpx").write_text(_gpx_with_start(45.501689, -73.576))
    a = _run(db, fit_filename="activities/1.gpx")
    a.moving_time_s = 1500
    shoe = OwnedShoe(brand="Brooks", model="Hyperion", starting_mileage=100.0, current_mileage=105.0)
    db.add(shoe)
    db.commit()
    db.add(ShoeRun(activity_id=a.id, owned_shoe_id=shoe.id))
    db.commit()

    svc.scan_archive(db, tmp_path)

    db.refresh(a)
    assert (a.start_lat, a.start_lng) == (45.502, -73.576)     # rounded to 3 decimals (~100 m)
    assert a.distance_km == 5.0 and a.moving_time_s == 1500    # not rewritten by the scan
    assert db.get(OwnedShoe, shoe.id).current_mileage == 105.0 # INV-1: the ledger is untouched
    run = db.query(ShoeRun).filter_by(activity_id=a.id).one()  # INV-2: attribution untouched
    assert run.owned_shoe_id == shoe.id
    assert _efforts(db, a.id)                                  # the efforts still landed


def test_archive_fit_gz_scan_stamps_start_from_semicircles(db, tmp_path):
    import gzip
    (tmp_path / "activities").mkdir()
    records = [(T0 + s, semicircles(45.501689), semicircles(-73.576), s * 3.0) for s in range(0, 400)]
    (tmp_path / "activities" / "1.fit.gz").write_bytes(gzip.compress(fit_bytes(records)))
    a = _run(db, fit_filename="activities/1.fit.gz")

    s = svc.scan_archive(db, tmp_path)
    assert (s.scanned, s.failed) == (1, 0)
    db.refresh(a)
    assert (a.start_lat, a.start_lng) == (45.502, -73.576)


def test_file_without_position_leaves_start_none_and_scan_succeeds(db, tmp_path):
    (tmp_path / "activities").mkdir()
    records = [(T0 + s, None, None, s * 3.0) for s in range(0, 400)]   # treadmill-style: no GPS
    (tmp_path / "activities" / "1.fit").write_bytes(fit_bytes(records))
    a = _run(db, fit_filename="activities/1.fit")

    s = svc.scan_archive(db, tmp_path)
    assert (s.scanned, s.failed) == (1, 0)
    db.refresh(a)
    assert a.start_lat is None and a.start_lng is None
    assert _efforts(db, a.id)                                  # distance still gives efforts


# ── Per-km splits and the version-upgrade rescan (R5.4.3) ────────────────────

def _splits(db, activity_id):
    return (db.query(ActivitySplit).filter(ActivitySplit.activity_id == activity_id)
            .order_by(ActivitySplit.split_index).all())


def _archive_run(db, tmp_path, km=5.2, pace_s_per_km=300, name="1.gpx"):
    (tmp_path / "activities").mkdir(exist_ok=True)
    text_ = _gpx(km, pace_s_per_km)
    (tmp_path / "activities" / name).write_text(text_)
    return _run(db, fit_filename=f"activities/{name}"), text_


def test_archive_scan_writes_splits_matching_the_engine_and_rescan_replaces_them(db, tmp_path):
    a, text_ = _archive_run(db, tmp_path)
    expected = svc.engine.km_splits(svc.engine.gpx_stream(text_), source="gpx")

    s = svc.scan_archive(db, tmp_path)
    rows = _splits(db, a.id)
    assert len(rows) == len(expected) == 6                      # five full km + a 200 m tail
    assert s.splits == len(expected)
    assert [(r.split_index, r.distance_m, r.elapsed_s, r.moving_s, r.source) for r in rows] == \
        [(sp.index, sp.distance_m, sp.elapsed_s, sp.moving_s, "gpx") for sp in expected]
    assert sum(r.elapsed_s for r in rows) == sum(sp.elapsed_s for sp in expected)

    svc.scan_archive(db, tmp_path, rescan=True)
    assert len(_splits(db, a.id)) == len(expected)              # replaced, not duplicated


def test_splits_die_with_their_activity(db, tmp_path):
    db.execute(text("PRAGMA foreign_keys=ON"))               # production enables this per connection
    a, _ = _archive_run(db, tmp_path, km=1.2)
    svc.scan_archive(db, tmp_path)
    assert db.query(ActivitySplit).count() > 0
    db.delete(a)
    db.commit()
    assert db.query(ActivitySplit).count() == 0


def test_stored_scan_records_the_current_version(db, tmp_path):
    a, _ = _archive_run(db, tmp_path, km=1.2)
    svc.scan_archive(db, tmp_path)
    assert db.get(ActivityEffortScan, a.id).scan_version == svc.SCAN_VERSION == 2


def test_version_1_ok_scan_is_rescanned_once_for_splits(db, tmp_path):
    a, _ = _archive_run(db, tmp_path)
    svc.scan_archive(db, tmp_path)
    scan = db.get(ActivityEffortScan, a.id)
    db.query(ActivitySplit).delete()                            # as a pre-R5.4.3 scan left it
    scan.scan_version = 1
    db.commit()

    first = svc.scan_archive(db, tmp_path)                      # plain, no rescan flag
    assert (first.scanned, first.splits) == (1, 6)
    assert len(_splits(db, a.id)) == 6
    db.refresh(scan)
    assert scan.scan_version == 2

    second = svc.scan_archive(db, tmp_path)
    assert second.scanned == 0                                  # a version-2 ok scan is settled


def test_upgrade_does_not_repick_no_stream_or_exhausted_failed_scans(db, tmp_path):
    (tmp_path / "activities").mkdir()
    short = _run(db, fit_filename="activities/short.gpx")
    (tmp_path / "activities" / "short.gpx").write_text(_gpx(0.0))   # a single point: no usable stream
    gone = _run(db, fit_filename="activities/gone.gpx")
    db.add_all([
        ActivityEffortScan(activity_id=short.id, status="no_stream", attempts=1, scan_version=1),
        ActivityEffortScan(activity_id=gone.id, status="failed", attempts=svc.MAX_SCAN_ATTEMPTS, scan_version=1),
    ])
    db.commit()

    s = svc.scan_archive(db, tmp_path)
    assert (s.scanned, s.no_stream, s.failed) == (0, 0, 0)
    assert db.query(ActivitySplit).count() == 0


def test_upgrade_picks_an_ok_row_with_budget_left_and_skips_an_exhausted_one(db, tmp_path):
    a, _ = _archive_run(db, tmp_path)
    spent, _ = _archive_run(db, tmp_path, name="2.gpx")
    db.add_all([
        ActivityEffortScan(activity_id=a.id, status="ok", source="gpx", attempts=1, scan_version=1),
        ActivityEffortScan(activity_id=spent.id, status="ok", source="gpx",
                           attempts=svc.MAX_SCAN_ATTEMPTS, scan_version=1),
    ])
    db.commit()
    assert svc.scan_archive(db, tmp_path).scanned == 1          # attempts counts tries for this version
    assert _splits(db, spent.id) == []
    assert len(_splits(db, a.id)) == 6


def test_coros_scan_upgrades_a_version_1_run_and_writes_splits(db, monkeypatch):
    stream = [(float(s), s * 1000 / 240) for s in range(0, 601)]   # 2.5 km at 4:00/km
    monkeypatch.setattr(svc.engine, "fit_records", lambda data: (stream, [None] * len(stream), [None] * len(stream)))
    old = _run(db, source="coros", coros_id="OLD", d=date(2026, 10, 1))
    settled = _run(db, source="coros", coros_id="NEW", d=date(2026, 10, 2))
    db.add_all([
        ActivityEffortScan(activity_id=old.id, status="ok", source="fit", attempts=1, scan_version=1),
        ActivityEffortScan(activity_id=settled.id, status="ok", source="fit", attempts=1, scan_version=svc.SCAN_VERSION),
    ])
    db.commit()
    client = _Client()

    s = svc.scan_coros(db, client, limit=5, get=lambda url, timeout: _Resp())
    assert client.asked == ["OLD"]                              # the settled current-version run is skipped
    assert (s.scanned, s.splits) == (1, 3)                      # two full km + a 500 m tail
    assert [(r.distance_m, r.elapsed_s) for r in _splits(db, old.id)] == [(1000, 240), (1000, 240), (500, 120)]
    assert db.get(ActivityEffortScan, old.id).scan_version == 2
    assert _splits(db, settled.id) == []

    # The COROS download ration still applies to upgrade rescans, newest first.
    for i in range(3):
        a = _run(db, source="coros", coros_id=f"V1-{i}", d=date(2026, 10, 10 + i))
        db.add(ActivityEffortScan(activity_id=a.id, status="ok", source="fit", attempts=1, scan_version=1))
    db.commit()
    client = _Client()
    svc.scan_coros(db, client, limit=2, get=lambda url, timeout: _Resp())
    assert client.asked == ["V1-2", "V1-1"]


def test_failed_upgrade_keeps_an_ok_row_ok_and_is_retried_then_left_alone(db, tmp_path):
    a, _ = _archive_run(db, tmp_path)
    svc.scan_archive(db, tmp_path)
    efforts_before = _efforts(db, a.id)
    scan = db.get(ActivityEffortScan, a.id)
    db.query(ActivitySplit).delete()
    scan.scan_version = 1                                       # as a pre-R5.4.3 scan left it
    db.commit()
    (tmp_path / "activities" / "1.gpx").unlink()                # the upgrade rescan will now fail

    for expected_attempts in range(2, svc.MAX_SCAN_ATTEMPTS + 1):
        s = svc.scan_archive(db, tmp_path)
        assert (s.scanned, s.failed) == (0, 1)
        db.refresh(scan)
        assert (scan.status, scan.scan_version, scan.attempts) == ("ok", 1, expected_attempts)
        assert scan.error and scan.source == "gpx"              # error recorded, source kept
        assert _efforts(db, a.id) == efforts_before             # efforts survive the rollback
    again = svc.scan_archive(db, tmp_path)
    assert (again.scanned, again.failed) == (0, 0)              # budget spent: left alone
    db.refresh(scan)
    assert scan.attempts == svc.MAX_SCAN_ATTEMPTS and scan.status == "ok"


def test_successful_scan_resets_attempts_to_one(db, tmp_path):
    a, _ = _archive_run(db, tmp_path)
    db.add(ActivityEffortScan(activity_id=a.id, status="failed", attempts=2, scan_version=1))
    db.commit()
    svc.scan_archive(db, tmp_path)
    scan = db.get(ActivityEffortScan, a.id)
    assert (scan.status, scan.attempts, scan.scan_version) == ("ok", 1, svc.SCAN_VERSION)
    svc.scan_archive(db, tmp_path, rescan=True)
    db.refresh(scan)
    assert scan.attempts == 1                                   # a rescan does not accumulate


def test_stored_splits_carry_avg_hr_and_elevation(db, tmp_path):
    from datetime import datetime, timedelta
    (tmp_path / "activities").mkdir()
    t0 = datetime(2020, 1, 1, 10, 0, 0)
    step_m = 10 * 1000 / 300                                   # 5:00/km, one point per 10 s
    pts = "".join(
        f'<trkpt lat="{45.5 + i * step_m / 111_195:.7f}" lon="-73.6"><ele>{100 + i * 0.5}</ele>'
        f'<time>{(t0 + timedelta(seconds=10 * i)).isoformat()}Z</time>'
        f'<extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>150</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>'
        for i in range(int(2.2 * 1000 / step_m) + 1)
    )
    (tmp_path / "activities" / "1.gpx").write_text(
        '<?xml version="1.0"?><gpx version="1.1" creator="t" xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"><trk><trkseg>' + pts + '</trkseg></trk></gpx>')
    a = _run(db, fit_filename="activities/1.gpx")

    svc.scan_archive(db, tmp_path)
    rows = _splits(db, a.id)
    assert [r.distance_m for r in rows][:2] == [1000, 1000]
    assert all(r.avg_hr == 150 for r in rows)
    assert rows[0].elev_gain_m == pytest.approx(0.5 * 1000 / step_m, abs=1.0)   # 0.5 m per point
    assert rows[0].elev_loss_m == 0.0


def test_stored_splits_without_hr_or_altitude_are_null(db, tmp_path):
    a, _ = _archive_run(db, tmp_path, km=1.2)                  # the plain _gpx has neither channel
    svc.scan_archive(db, tmp_path)
    row = _splits(db, a.id)[0]
    assert (row.avg_hr, row.elev_gain_m, row.elev_loss_m) == (None, None, None)


def test_coros_scan_stores_hr_and_elevation_from_fit_records(db, monkeypatch):
    n = 301
    stream = [(float(s), s * 1000 / 240) for s in range(n)]    # 1.25 km
    monkeypatch.setattr(svc.engine, "fit_records",
                        lambda data: (stream, [160.0] * n, [50.0 + s * 0.1 for s in range(n)]))
    a = _run(db, source="coros", coros_id="L1", d=date(2026, 10, 1))
    svc.scan_coros(db, _Client(), limit=1, get=lambda url, timeout: _Resp())
    rows = _splits(db, a.id)
    assert rows[0].avg_hr == 160 and rows[0].elev_gain_m == pytest.approx(24.0, abs=0.2)
