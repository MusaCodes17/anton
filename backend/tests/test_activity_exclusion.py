"""Tests for R11.4 storage + edit path -- excluding an activity from analysis.

The flag removes a run from DERIVED analytics only (via the
`unified_activities(for_analysis=True)` seam option); it must never move shoe
mileage or volume totals (INV-1/INV-2). No analytics consumer is wired yet --
that is a later R11.4 task -- so these tests pin the column, the PATCH rules,
and the seam.

PATCH rules are driven through a minimal FastAPI app that mounts only the
activities router (a StaticPool in-memory DB via a `get_db` override), so the
suite needs no auth env and no `app.main` import-order assumptions.
"""
import asyncio
from datetime import date

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import models  # noqa: F401 -- registers tables on Base.metadata
from app.models.models import Activity, OwnedShoe
from app.routers import activities as activities_router
from app.services import activities as activities_svc
from app.services import rotation, strava_stats
from app.utils.exclusion_reasons import EXCLUDE_REASONS


class _SyncClient:
    """Tiny sync wrapper over httpx's ASGITransport -- Starlette's TestClient is
    incompatible with the pinned httpx (same reason test_auth drives ASGI directly)."""

    def __init__(self, app):
        self._app = app

    def request(self, method, url, **kw):
        async def _go():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
                return await c.request(method, url, **kw)
        return asyncio.run(_go())

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def patch(self, url, **kw):
        return self.request("PATCH", url, **kw)


@pytest.fixture()
def client_and_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    def _override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app = FastAPI()
    app.include_router(activities_router.router, prefix="/api")
    app.dependency_overrides[get_db] = _override
    session = Session()
    try:
        yield _SyncClient(app), session
    finally:
        session.close()
        engine.dispose()


def _run(session, **kw):
    a = Activity(source="manual", activity_type="Run", run_date=kw.pop("run_date", date(2026, 7, 1)),
                 distance_km=kw.pop("distance_km", 10.0), name="Run", **kw)
    session.add(a); session.commit(); session.refresh(a)
    return a


def test_vocabulary_is_the_decided_list():
    assert EXCLUDE_REASONS == ("gps_error", "wrong_sport", "duplicate", "treadmill_calibration", "other")


def test_patch_sets_exclusion_with_reason_and_note(client_and_session):
    client, s = client_and_session
    a = _run(s)
    r = client.patch(f"/api/activities/{a.id}", json={
        "exclude_from_analysis": True, "exclude_reason": "gps_error", "exclude_note": "tunnel spike"})
    assert r.status_code == 200
    body = r.json()
    assert body["exclude_from_analysis"] is True
    assert body["exclude_reason"] == "gps_error"
    assert body["exclude_note"] == "tunnel spike"
    # Detail GET agrees.
    got = client.get(f"/api/activities/{a.id}").json()
    assert (got["exclude_from_analysis"], got["exclude_reason"], got["exclude_note"]) == (True, "gps_error", "tunnel spike")


def test_new_activity_defaults_to_included(client_and_session):
    client, s = client_and_session
    a = _run(s)
    body = client.get(f"/api/activities/{a.id}").json()
    assert body["exclude_from_analysis"] is False
    assert body["exclude_reason"] is None and body["exclude_note"] is None


def test_exclude_without_reason_is_400_and_writes_nothing(client_and_session):
    client, s = client_and_session
    a = _run(s)
    r = client.patch(f"/api/activities/{a.id}", json={"exclude_from_analysis": True, "name": "Renamed"})
    assert r.status_code == 400
    s.expire_all()
    row = s.get(Activity, a.id)
    assert row.exclude_from_analysis is False
    assert row.name == "Run"  # the rejected edit did not partially apply


def test_exclude_uses_reason_already_on_the_row(client_and_session):
    client, s = client_and_session
    a = _run(s, exclude_reason="duplicate")
    r = client.patch(f"/api/activities/{a.id}", json={"exclude_from_analysis": True})
    assert r.status_code == 200
    assert r.json()["exclude_reason"] == "duplicate"


def test_bad_reason_is_422(client_and_session):
    client, s = client_and_session
    a = _run(s)
    r = client.patch(f"/api/activities/{a.id}", json={"exclude_from_analysis": True, "exclude_reason": "bored"})
    assert r.status_code == 422


def test_service_guards_bad_reason_too(db):
    a = _run(db)
    with pytest.raises(ValueError):
        activities_svc.update_activity(db, a.id, exclude_from_analysis=True, exclude_reason="bored")
    with pytest.raises(ValueError):
        activities_svc.update_activity(db, a.id, exclude_from_analysis=True)
    db.refresh(a)
    assert a.exclude_from_analysis is False


def test_unexclude_clears_reason_and_note(client_and_session):
    client, s = client_and_session
    a = _run(s)
    client.patch(f"/api/activities/{a.id}", json={
        "exclude_from_analysis": True, "exclude_reason": "wrong_sport", "exclude_note": "was a walk"})
    r = client.patch(f"/api/activities/{a.id}", json={"exclude_from_analysis": False})
    assert r.status_code == 200
    body = r.json()
    assert body["exclude_from_analysis"] is False
    assert body["exclude_reason"] is None and body["exclude_note"] is None


def test_other_edits_leave_exclusion_alone(client_and_session):
    client, s = client_and_session
    a = _run(s)
    client.patch(f"/api/activities/{a.id}", json={"exclude_from_analysis": True, "exclude_reason": "other"})
    body = client.patch(f"/api/activities/{a.id}", json={"name": "Renamed"}).json()
    assert body["name"] == "Renamed"
    assert body["exclude_from_analysis"] is True and body["exclude_reason"] == "other"


def test_unified_activities_for_analysis_drops_excluded(db):
    keep = _run(db, run_date=date(2026, 7, 1))
    gone = _run(db, run_date=date(2026, 7, 2))
    activities_svc.update_activity(db, gone.id, exclude_from_analysis=True, exclude_reason="gps_error")

    everything = activities_svc.unified_activities(db)
    assert {u.activity_id for u in everything} == {keep.id, gone.id}   # default unchanged
    flagged = {u.activity_id: u.exclude_from_analysis for u in everything}
    assert flagged == {keep.id: False, gone.id: True}

    analysed = activities_svc.unified_activities(db, for_analysis=True)
    assert [u.activity_id for u in analysed] == [keep.id]

    # Un-excluding brings it back.
    activities_svc.update_activity(db, gone.id, exclude_from_analysis=False)
    assert len(activities_svc.unified_activities(db, for_analysis=True)) == 2


def test_exclusion_never_moves_mileage_or_volume(db):
    shoe = OwnedShoe(brand="Nike", model="Pegasus", starting_mileage=100.0, current_mileage=100.0)
    db.add(shoe); db.commit(); db.refresh(shoe)
    res = rotation.log_run(db, shoe.id, distance_km=12.0, run_date=date(2026, 7, 6), source="manual")
    before_mileage = db.get(OwnedShoe, shoe.id).current_mileage
    before_weekly = [(p.period, p.total_km, p.run_count) for p in strava_stats.training_summary(db, "weekly")]
    assert before_mileage == pytest.approx(112.0)

    activities_svc.update_activity(db, res.activity.id, exclude_from_analysis=True, exclude_reason="duplicate")
    db.expire_all()
    assert db.get(OwnedShoe, shoe.id).current_mileage == pytest.approx(before_mileage)
    assert [(p.period, p.total_km, p.run_count) for p in strava_stats.training_summary(db, "weekly")] == before_weekly
    assert db.get(Activity, res.activity.id).distance_km == pytest.approx(12.0)

    activities_svc.update_activity(db, res.activity.id, exclude_from_analysis=False)
    db.expire_all()
    assert db.get(OwnedShoe, shoe.id).current_mileage == pytest.approx(before_mileage)
    assert [(p.period, p.total_km, p.run_count) for p in strava_stats.training_summary(db, "weekly")] == before_weekly


# ── R11.4 consumer wiring: derived analytics skip excluded runs ──────────────────────────
from datetime import timedelta  # noqa: E402

from app.models.models import ActivityBestEffort, ActivityEffortScan, PlannedRace  # noqa: E402
from app.services import race_advisor, training_trends  # noqa: E402

AS_OF = date(2026, 10, 9)
RACE_DAY = date(2026, 10, 11)


def _exclude(db, a):
    activities_svc.update_activity(db, a.id, exclude_from_analysis=True, exclude_reason="gps_error")


def _marathon(db, day=RACE_DAY, **kw):
    r = PlannedRace(name="M", race_date=day, distance_km=42.195, target_time_s=10800,
                    status=kw.pop("status", "planned"), **kw)
    db.add(r); db.commit()
    return r


def _segment(db, a, label, elapsed_s):
    db.add(ActivityEffortScan(activity_id=a.id, status="ok", source="fit"))
    db.add(ActivityBestEffort(activity_id=a.id, distance_label=label, elapsed_s=elapsed_s,
                              start_offset_m=0, source="fit"))
    db.commit()


def test_readiness_skips_excluded_long_run_and_peak_week(db):
    _marathon(db)
    big = _run(db, run_date=date(2026, 9, 15), distance_km=35.0)    # 2026-W38, would be the peak
    _run(db, run_date=date(2026, 9, 22), distance_km=30.0)          # 2026-W39
    _exclude(db, big)
    rd = race_advisor.race_readiness(db, as_of=AS_OF)
    assert rd.block_runs == 1 and rd.block_km == 30.0
    assert [r.distance_km for r in rd.long_runs] == [30.0]
    assert all(r.activity_id != big.id for r in rd.long_runs)
    assert rd.longest_run.distance_km == 30.0
    assert rd.peak_week.period == "2026-W39" and rd.peak_week.total_km == 30.0


def test_readiness_key_effort_ignores_excluded_fast_effort(db):
    _marathon(db)
    fast = _run(db, run_date=AS_OF - timedelta(days=20), distance_km=25.0, elapsed_time_s=7500)
    slow = _run(db, run_date=AS_OF - timedelta(days=19), distance_km=25.0, elapsed_time_s=7500)
    _segment(db, fast, "half", 4200)     # ~199 s/km
    _segment(db, slow, "half", 6000)     # ~284 s/km
    _exclude(db, fast)
    rd = race_advisor.race_readiness(db, as_of=AS_OF)
    half = next(e for e in rd.recent_efforts if e.label == "half")
    assert half.time_s == 6000 and half.activity_id == slow.id
    key = next(i for i in rd.checklist if i.key == "key_effort")
    assert key.value == round(6000 / 21.0975)


def test_block_comparison_skips_excluded_run(db):
    block_start = date(2025, 11, 10)
    _marathon(db, day=date(2026, 3, 1), status="completed")
    _run(db, run_date=block_start + timedelta(days=1), distance_km=28.0)
    bad = _run(db, run_date=block_start + timedelta(days=2), distance_km=40.0)
    _exclude(db, bad)
    b = race_advisor.block_comparison(db, as_of=AS_OF).blocks[0]
    assert b.runs == 1 and b.total_km == 28.0 and b.long_runs == 1
    assert b.longest_run.distance_km == 28.0


def test_load_trend_skips_excluded_run(db):
    _run(db, run_date=AS_OF - timedelta(days=2), distance_km=10.0)
    bad = _run(db, run_date=AS_OF - timedelta(days=1), distance_km=40.0)
    _run(db, run_date=AS_OF - timedelta(days=20), distance_km=20.0)
    _exclude(db, bad)
    t = training_trends.load_trend(db, as_of=AS_OF)
    assert t.last7_km == 10.0 and t.last7_runs == 1 and t.last7_longest_km == 10.0


def test_form_trend_best_efforts_skip_excluded_run(db):
    fast = _run(db, run_date=AS_OF - timedelta(days=3))
    slow = _run(db, run_date=AS_OF - timedelta(days=4))
    _segment(db, fast, "5k", 1000)
    _segment(db, slow, "5k", 1100)
    _exclude(db, fast)
    five = next(b for b in training_trends.form_trend(db, as_of=AS_OF).best_efforts if b.label == "5k")
    assert five.recent.activity_id == slow.id and five.all_time.time_s == 1100


def test_personal_bests_drops_excluded_effort_but_keeps_race_pb(db):
    fast = _run(db, run_date=date(2026, 6, 1), distance_km=5.0, moving_time_s=1000,
                elapsed_time_s=1000, activity_tag="Race")
    _segment(db, fast, "5k", 1000)
    _exclude(db, fast)
    pbs = strava_stats.personal_bests(db)
    assert all(b.activity_id != fast.id for b in pbs.best_efforts)
    assert any(b.activity_id == fast.id for b in pbs.race_pbs)   # official record stays


def test_volume_and_mileage_unchanged_by_exclusion(db):
    shoe = OwnedShoe(brand="Nike", model="Pegasus", starting_mileage=0.0, current_mileage=0.0)
    db.add(shoe); db.commit(); db.refresh(shoe)
    res = rotation.log_run(db, shoe.id, distance_km=12.0, run_date=date(2026, 7, 6), source="manual")
    before = [(p.period, p.total_km, p.run_count) for p in strava_stats.training_summary(db, "weekly")]
    _exclude(db, res.activity)
    db.expire_all()
    assert [(p.period, p.total_km, p.run_count) for p in strava_stats.training_summary(db, "weekly")] == before
    assert db.get(OwnedShoe, shoe.id).current_mileage == pytest.approx(12.0)
