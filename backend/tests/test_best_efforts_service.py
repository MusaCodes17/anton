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
  - efforts die with their activity.
"""
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.models import Activity, ActivityBestEffort, ActivityEffortScan, CorosConnection
from app.services import best_efforts as svc
from app.services import coros_poller as poller
from app.services.coros_mcp_client import CorosContractError, parse_fit_url

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
    monkeypatch.setattr(svc.engine, "fit_stream", lambda data: stream)
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
