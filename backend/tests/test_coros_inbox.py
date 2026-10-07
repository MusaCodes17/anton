"""COROS direct sync §6 backend — the "New runs" inbox.

Rules under test: confirm goes through the single run writer exactly once even
when retried or when the run was already logged by another path (INV-1/INV-5),
dismissed/confirmed rows leave the list, the 600/700/800 advisories and 100 km
checkpoints surface, and a failed confirm leaves the pending row untouched.
"""
import os
from datetime import date

os.environ.setdefault("ANTON_TOKENS", "desktop:test-inbox-token-0123456789abcdef")

import pytest

from app.models.models import Activity, OwnedShoe, PendingCorosRun, ShoeRun
from app.services import coros as coros_svc
from app.services import coros_inbox as inbox
from app.services import rotation


def mk_shoe(db, mileage=100.0, **kw):
    s = OwnedShoe(brand="Nike", model="Pegasus", shoe_type="daily_trainer", starting_mileage=mileage,
                  current_mileage=mileage, status="active", **kw)
    db.add(s)
    db.commit()
    return s


def mk_pending(db, label="480000000000000001", **kw):
    vals = dict(label_id=label, sport_type=100, run_date=date(2026, 10, 6), distance_km=12.53,
                moving_time_s=3159, elapsed_time_s=3163, avg_pace_s_per_km=252, avg_hr=171,
                calories=710.0, elevation_gain_m=60.0, avg_cadence=186.0, training_load=113.0,
                training_focus="Base", start_timestamp=1791333579, end_timestamp=1791336739,
                status="pending")
    vals.update(kw)
    r = PendingCorosRun(**vals)
    db.add(r)
    db.commit()
    return r


# --- list --------------------------------------------------------------------------

def test_list_is_newest_first_and_hides_resolved(db):
    a = mk_pending(db, "1", run_date=date(2026, 10, 3))
    b = mk_pending(db, "2", run_date=date(2026, 10, 6), start_timestamp=100)
    c = mk_pending(db, "3", run_date=date(2026, 10, 6), start_timestamp=200)
    mk_pending(db, "4", status="dismissed")
    mk_pending(db, "5", status="confirmed")
    assert [r["label_id"] for r in inbox.list_pending(db)] == ["3", "2", "1"]
    r = inbox.list_pending(db)[0]
    assert r["avg_pace"] == "4:12/km" and r["distance_km"] == 12.53


# --- confirm ------------------------------------------------------------------------

def test_confirm_logs_once_through_the_writer_with_all_fields(db):
    shoe = mk_shoe(db, 100.0)
    p = mk_pending(db)
    out = inbox.confirm(db, p.id, owned_shoe_id=shoe.id)
    assert out["logged"] is True and out["shoe"]["new_mileage"] == 112.53
    act = db.query(Activity).one()
    assert act.source == "coros" and act.coros_activity_id == "480000000000000001"
    assert act.run_date == date(2026, 10, 6) and act.avg_pace_s_per_km == 252
    assert (act.elapsed_time_s, act.elevation_gain_m, act.avg_cadence) == (3163, 60.0, 186.0)
    assert (act.training_load, act.training_focus, act.avg_hr) == (113.0, "Base", 171)
    assert db.query(ShoeRun).one().owned_shoe_id == shoe.id
    db.refresh(p)
    assert p.status == "confirmed" and p.resolved_at is not None
    assert inbox.list_pending(db) == []


def test_runner_can_override_the_suggested_shoe(db):
    suggested, chosen = mk_shoe(db, 10.0), mk_shoe(db, 200.0)
    p = mk_pending(db, suggested_shoe_id=suggested.id)
    inbox.confirm(db, p.id, owned_shoe_id=chosen.id)
    db.refresh(suggested), db.refresh(chosen)
    assert suggested.current_mileage == 10.0 and chosen.current_mileage == 212.53


def test_retrying_confirm_never_double_logs(db):
    shoe = mk_shoe(db, 100.0)
    p = mk_pending(db)
    inbox.confirm(db, p.id, owned_shoe_id=shoe.id)
    again = inbox.confirm(db, p.id, owned_shoe_id=shoe.id)
    assert again["logged"] is False and again["already_logged"] is True
    assert db.query(Activity).count() == 1
    db.refresh(shoe)
    assert shoe.current_mileage == 112.53


def test_crash_between_log_and_mark_heals_on_retry(db):
    shoe = mk_shoe(db, 100.0)
    p = mk_pending(db)
    # the run got logged but the pending row was never marked (crash / other path)
    coros_svc.confirm_run(db, coros_activity_id=p.label_id, owned_shoe_id=shoe.id,
                          run_date=p.run_date, distance_km=p.distance_km)
    out = inbox.confirm(db, p.id, owned_shoe_id=shoe.id)
    assert out["already_logged"] is True and out["logged"] is False
    db.refresh(p), db.refresh(shoe)
    assert p.status == "confirmed" and db.query(Activity).count() == 1 and shoe.current_mileage == 112.53


def test_failed_confirm_leaves_pending_untouched(db):
    shoe = mk_shoe(db)
    p = mk_pending(db)
    with pytest.raises(LookupError):
        inbox.confirm(db, p.id, owned_shoe_id=9999)
    with pytest.raises(ValueError):
        inbox.confirm(db, p.id, owned_shoe_id=shoe.id, activity_tag="Bogus")
    with pytest.raises(LookupError):
        inbox.confirm(db, 424242, owned_shoe_id=shoe.id)
    db.refresh(p)
    assert p.status == "pending" and db.query(Activity).count() == 0


def test_valid_tag_and_notes_pass_through(db):
    shoe = mk_shoe(db)
    p = mk_pending(db)
    inbox.confirm(db, p.id, owned_shoe_id=shoe.id, activity_tag="Tempo", notes="felt good")
    act = db.query(Activity).one()
    assert act.activity_tag == "Tempo" and "felt good" in (act.description or "")


def test_threshold_and_checkpoint_surface_on_confirm(db):
    shoe = mk_shoe(db, 595.0)
    p = mk_pending(db, distance_km=12.0)       # 595 -> 607: crosses 600 km and the 600 checkpoint
    out = inbox.confirm(db, p.id, owned_shoe_id=shoe.id)
    assert out["threshold_crossed"] == 600 and "replacement" in out["threshold_message"]
    assert out["checkpoint_reached"] is True and out["checkpoint_km"] == 600


def test_no_threshold_when_none_crossed(db):
    shoe = mk_shoe(db, 100.0)
    out = inbox.confirm(db, mk_pending(db).id, owned_shoe_id=shoe.id)
    assert out["threshold_crossed"] is None and out["checkpoint_reached"] is False


def test_threshold_boundaries():
    assert rotation.threshold_crossed_by(599.9, 600.0)[0] == 600     # landing exactly on it counts
    assert rotation.threshold_crossed_by(600.0, 650.0) is None       # already past it
    assert rotation.threshold_crossed_by(690.0, 810.0)[0] == 700     # lowest crossed is reported
    assert rotation.threshold_crossed_by(0, 10) is None


# --- dismiss ------------------------------------------------------------------------

def test_dismiss_keeps_row_logs_nothing_and_is_idempotent(db):
    p = mk_pending(db)
    assert inbox.dismiss(db, p.id) == {"dismissed": True}
    inbox.dismiss(db, p.id)
    db.refresh(p)
    assert p.status == "dismissed" and p.resolved_at is not None
    assert db.query(Activity).count() == 0 and inbox.list_pending(db) == []


def test_dismissed_cannot_be_confirmed_nor_confirmed_dismissed(db):
    shoe = mk_shoe(db)
    d = mk_pending(db, "d")
    inbox.dismiss(db, d.id)
    with pytest.raises(ValueError):
        inbox.confirm(db, d.id, owned_shoe_id=shoe.id)
    c = mk_pending(db, "c")
    inbox.confirm(db, c.id, owned_shoe_id=shoe.id)
    with pytest.raises(ValueError):
        inbox.dismiss(db, c.id)


# --- HTTP -----------------------------------------------------------------------------

@pytest.fixture()
def http():
    import asyncio
    import httpx
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.database import Base, get_db
    from app.main import app
    from app.services.rate_limit import auth_failure_limiter

    auth_failure_limiter._buckets.clear()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    S = sessionmaker(bind=engine)

    def _db():
        s = S()
        try:
            yield s
        finally:
            s.close()

    prev = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _db
    tok = dict(p.split(":", 1) for p in os.environ["ANTON_TOKENS"].split(","))["desktop"]

    def call(method, path, json=None, auth=True):
        headers = {"Authorization": f"Bearer {tok}"} if auth else {}

        async def _go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
                return await c.request(method, path, headers=headers, json=json)
        return asyncio.run(_go())

    call.session = S
    yield call
    if prev is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = prev


def test_inbox_endpoints_require_auth(http):
    assert http("GET", "/api/coros/pending", auth=False).status_code == 401
    assert http("POST", "/api/coros/pending/1/confirm", json={"owned_shoe_id": 1}, auth=False).status_code == 401
    assert http("POST", "/api/coros/pending/1/dismiss", auth=False).status_code == 401


def test_inbox_http_round_trip_and_error_mapping(http):
    s = http.session()
    shoe = mk_shoe(s, 100.0)
    p = mk_pending(s)
    sid, pid = shoe.id, p.id
    s.close()
    listing = http("GET", "/api/coros/pending").json()
    assert [r["id"] for r in listing["runs"]] == [pid]
    r = http("POST", f"/api/coros/pending/{pid}/confirm", json={"owned_shoe_id": sid})
    assert r.status_code == 200 and r.json()["logged"] is True
    assert http("POST", f"/api/coros/pending/{pid}/confirm", json={"owned_shoe_id": sid}).json()["already_logged"] is True
    assert http("GET", "/api/coros/pending").json()["runs"] == []
    assert http("POST", "/api/coros/pending/999/confirm", json={"owned_shoe_id": sid}).status_code == 404
    assert http("POST", "/api/coros/pending/999/dismiss").status_code == 404
    assert http("POST", f"/api/coros/pending/{pid}/dismiss").status_code == 400   # already logged
