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


def test_confirm_carries_location_onto_the_activity_and_dict_hides_coordinates(db):
    shoe = mk_shoe(db, 100.0)
    p = mk_pending(db, location_label="Montreal Run", start_lat=45.502, start_lng=-73.567)
    d = inbox.pending_to_dict(p)
    assert d["location_label"] == "Montreal Run" and "start_lat" not in d and "start_lng" not in d
    inbox.confirm(db, p.id, owned_shoe_id=shoe.id)
    act = db.query(Activity).one()
    assert (act.location_label, act.start_lat, act.start_lng) == ("Montreal Run", 45.502, -73.567)


def test_confirm_run_without_location_kwargs_uses_the_pending_row(db):
    shoe = mk_shoe(db, 100.0)
    mk_pending(db, location_label="Montreal Run", start_lat=45.502, start_lng=-73.567)
    coros_svc.confirm_run(db, coros_activity_id="480000000000000001", owned_shoe_id=shoe.id,
                          run_date=date(2026, 10, 6), distance_km=12.53)
    act = db.query(Activity).one()
    assert (act.location_label, act.start_lat, act.start_lng) == ("Montreal Run", 45.502, -73.567)


# --- inbox_view ---------------------------------------------------------------------

def test_inbox_view_rotation_lists_active_shoes_only(db):
    active = mk_shoe(db, 120.0)
    retired = mk_shoe(db, 50.0)
    retired.status = "retired"
    for_sale = mk_shoe(db, 30.0)
    for_sale.status = "for_sale"
    db.commit()
    view = inbox.inbox_view(db)
    assert [s.id for s in view.rotation] == [active.id]
    assert view.rotation[0].current_mileage_km == 120.0 and view.rotation[0].shoe_type == "daily_trainer"


def test_inbox_view_retired_suggestion_refreshes_without_writing_back(db):
    retired = mk_shoe(db, 50.0)
    retired.status = "retired"
    db.commit()
    active = mk_shoe(db, 300.0)
    p = mk_pending(db, suggested_shoe_id=retired.id, suggestion_reason="old reason")
    run = inbox.inbox_view(db).runs[0]
    assert run.suggested_shoe_id == active.id and run.suggested_shoe == "Nike Pegasus"
    assert run.suggestion_refreshed is True and run.suggestion_reason != "old reason"
    db.expire_all()
    row = db.get(PendingCorosRun, p.id)
    assert row.suggested_shoe_id == retired.id and row.suggestion_reason == "old reason"


def test_inbox_view_retired_suggestion_with_no_active_shoe_left(db):
    retired = mk_shoe(db, 50.0)
    retired.status = "retired"
    db.commit()
    mk_pending(db, suggested_shoe_id=retired.id, suggestion_reason="old reason")
    run = inbox.inbox_view(db).runs[0]
    assert run.suggested_shoe_id is None and run.suggested_shoe is None
    assert run.suggestion_refreshed is True and "No active shoe" in run.suggestion_reason


def test_inbox_view_active_suggestion_names_shoe_with_nickname(db):
    shoe = mk_shoe(db, 100.0, nickname="Teal")
    mk_pending(db, suggested_shoe_id=shoe.id, suggestion_reason="stored reason")
    view = inbox.inbox_view(db)
    run = view.runs[0]
    assert run.suggested_shoe_id == shoe.id and run.suggested_shoe == "Nike Pegasus (Teal)"
    assert run.suggestion_refreshed is False and run.suggestion_reason == "stored reason"
    assert view.rotation[0].name == "Nike Pegasus (Teal)"


def test_inbox_view_empty(db):
    view = inbox.inbox_view(db)
    assert view.runs == [] and view.rotation == []


def test_inbox_view_excludes_dismissed_and_confirmed(db):
    shoe = mk_shoe(db, 100.0)
    p = mk_pending(db, "p")
    mk_pending(db, "d", status="dismissed")
    mk_pending(db, "c", status="confirmed")
    assert [r.pending_id for r in inbox.inbox_view(db).runs] == [p.id]


# --- resolve_batch ------------------------------------------------------------------

def _count_activities(db):
    return db.query(Activity).count()


def test_batch_mixed_partial_success_and_per_shoe_sums(db):
    a, b = mk_shoe(db, 100.0), mk_shoe(db, 200.0, nickname="Teal")
    p1 = mk_pending(db, "b1", distance_km=10.0)
    p2 = mk_pending(db, "b2", distance_km=5.5)
    p3 = mk_pending(db, "b3", distance_km=8.0)
    p4 = mk_pending(db, "b4")
    p5 = mk_pending(db, "b5")
    items = [
        inbox.BatchItem(p1.id, "confirm", owned_shoe_id=a.id),
        inbox.BatchItem(p5.id, "confirm", owned_shoe_id=99999),          # failing, in the middle
        inbox.BatchItem(p2.id, "confirm", owned_shoe_id=a.id),
        inbox.BatchItem(p3.id, "confirm", owned_shoe_id=b.id),
        inbox.BatchItem(p4.id, "dismiss"),
        inbox.BatchItem(424242, "dismiss"),                              # unknown pending id
    ]
    res = inbox.resolve_batch(db, items)
    assert (res.logged, res.dismissed, res.already_logged) == (3, 1, 0)
    assert {e["pending_id"] for e in res.errors} == {p5.id, 424242}
    assert [(s["shoe_id"], s["km_added"]) for s in res.per_shoe] == [(a.id, 15.5), (b.id, 8.0)]
    assert res.per_shoe[1]["name"] == "Nike Pegasus (Teal)"
    assert res.per_shoe[0]["new_mileage_km"] == pytest.approx(115.5)
    db.refresh(p5)
    assert p5.status == "pending"


def test_batch_ledger_round_trip(db):
    a, b = mk_shoe(db, 100.0), mk_shoe(db, 50.0)
    ps = [mk_pending(db, f"l{i}", distance_km=d) for i, d in enumerate([10.1, 7.37, 12.53])]
    res = inbox.resolve_batch(db, [
        inbox.BatchItem(ps[0].id, "confirm", owned_shoe_id=a.id),
        inbox.BatchItem(ps[1].id, "confirm", owned_shoe_id=a.id),
        inbox.BatchItem(ps[2].id, "confirm", owned_shoe_id=b.id),
    ])
    db.refresh(a)
    db.refresh(b)
    by = {s["shoe_id"]: s for s in res.per_shoe}
    assert by[a.id]["km_added"] == pytest.approx(a.current_mileage - 100.0)
    assert by[b.id]["km_added"] == pytest.approx(b.current_mileage - 50.0)


def test_batch_rerun_is_idempotent(db):
    shoe = mk_shoe(db, 100.0)
    ps = [mk_pending(db, f"r{i}") for i in range(2)]
    items = [inbox.BatchItem(p.id, "confirm", owned_shoe_id=shoe.id) for p in ps]
    inbox.resolve_batch(db, items)
    db.refresh(shoe)
    mileage, n_act = shoe.current_mileage, _count_activities(db)
    res = inbox.resolve_batch(db, items)
    db.refresh(shoe)
    assert (res.logged, res.already_logged, res.per_shoe) == (0, 2, [])
    assert shoe.current_mileage == mileage and _count_activities(db) == n_act


def test_batch_threshold_reported_once_per_shoe(db):
    shoe = mk_shoe(db, 590.0)
    ps = [mk_pending(db, f"t{i}") for i in range(2)]          # 12.53 km each: 602.53 then 615.06
    res = inbox.resolve_batch(db, [inbox.BatchItem(p.id, "confirm", owned_shoe_id=shoe.id) for p in ps])
    assert len(res.thresholds) == 1 and res.thresholds[0]["threshold_km"] == 600
    assert res.thresholds[0]["shoe_id"] == shoe.id and res.thresholds[0]["message"]


def test_batch_double_crossing_keeps_highest(db):
    shoe = mk_shoe(db, 595.0)
    p1 = mk_pending(db, "h1", distance_km=10.0)
    p2 = mk_pending(db, "h2", distance_km=100.0)
    res = inbox.resolve_batch(db, [
        inbox.BatchItem(p1.id, "confirm", owned_shoe_id=shoe.id),
        inbox.BatchItem(p2.id, "confirm", owned_shoe_id=shoe.id),
    ])
    assert [t["threshold_km"] for t in res.thresholds] == [700]


def test_batch_checkpoint_reported(db):
    shoe = mk_shoe(db, 95.0)
    p = mk_pending(db, "c1", distance_km=12.0)
    res = inbox.resolve_batch(db, [inbox.BatchItem(p.id, "confirm", owned_shoe_id=shoe.id)])
    assert [c["checkpoint_km"] for c in res.checkpoints] == [100]
    assert res.checkpoints[0]["shoe_id"] == shoe.id


def test_batch_duplicate_pending_id_raises_before_any_write(db):
    shoe = mk_shoe(db)
    p = mk_pending(db)
    with pytest.raises(ValueError, match=str(p.id)):
        inbox.resolve_batch(db, [
            inbox.BatchItem(p.id, "confirm", owned_shoe_id=shoe.id),
            inbox.BatchItem(p.id, "dismiss"),
        ])
    db.refresh(p)
    assert p.status == "pending" and _count_activities(db) == 0


def test_batch_confirm_without_shoe_never_uses_suggestion(db):
    shoe = mk_shoe(db)
    p = mk_pending(db, suggested_shoe_id=shoe.id, suggestion_reason="r")
    res = inbox.resolve_batch(db, [inbox.BatchItem(p.id, "confirm")])
    assert res.logged == 0 and res.errors == [
        {"pending_id": p.id, "error": "owned_shoe_id is required to confirm"}]
    db.refresh(p)
    assert p.status == "pending" and _count_activities(db) == 0


def test_batch_invalid_tag_only_fails_that_item(db):
    shoe = mk_shoe(db)
    bad, good = mk_pending(db, "g1"), mk_pending(db, "g2")
    res = inbox.resolve_batch(db, [
        inbox.BatchItem(bad.id, "confirm", owned_shoe_id=shoe.id, activity_tag="not-a-tag"),
        inbox.BatchItem(good.id, "confirm", owned_shoe_id=shoe.id),
    ])
    assert res.logged == 1 and [e["pending_id"] for e in res.errors] == [bad.id]
    db.refresh(bad)
    assert bad.status == "pending"


def test_batch_unknown_action_is_an_error(db):
    p = mk_pending(db)
    res = inbox.resolve_batch(db, [inbox.BatchItem(p.id, "explode")])
    assert res.errors == [{"pending_id": p.id, "error": "Unknown action 'explode'"}]


def test_batch_generic_exception_does_not_stop_loop(db, monkeypatch):
    shoe = mk_shoe(db)
    boom, ok = mk_pending(db, "x1"), mk_pending(db, "x2")
    real = inbox.confirm

    def fake(db_, pending_id, **kw):
        if pending_id == boom.id:
            raise RuntimeError("kaboom")
        return real(db_, pending_id, **kw)

    monkeypatch.setattr(inbox, "confirm", fake)
    res = inbox.resolve_batch(db, [
        inbox.BatchItem(boom.id, "confirm", owned_shoe_id=shoe.id),
        inbox.BatchItem(ok.id, "confirm", owned_shoe_id=shoe.id),
    ])
    assert res.errors == [{"pending_id": boom.id, "error": "Internal error"}]
    assert res.logged == 1


def test_batch_empty_list(db):
    assert inbox.resolve_batch(db, []) == inbox.BatchResult()
