"""Tests for R2.7 T5 — athlete fitness snapshots (append-only, latest wins)."""
from app.routers.training import get_fitness
from app.services import fitness as fitness_svc


def test_latest_is_none_when_empty(db):
    assert fitness_svc.latest(db) is None
    resp = get_fitness(db=db)
    assert resp.has_data is False
    assert resp.vo2max is None


def test_record_and_read_latest(db):
    fitness_svc.record_snapshot(db, vo2max=60.0, threshold_pace_s_per_km=230,
                                race_predictions={"5.0": 1005})
    newest = fitness_svc.record_snapshot(db, vo2max=62.5, threshold_pace_s_per_km=225,
                                         race_predictions={"5.0": 990, "10.0": 2100})
    # Append-only: both rows persist, latest() returns the newest.
    assert fitness_svc.latest(db).id == newest.id

    resp = get_fitness(db=db)
    assert resp.has_data is True
    assert resp.vo2max == 62.5
    assert resp.threshold_pace_s_per_km == 225
    assert resp.threshold_pace == "3:45/km"          # formatted at the boundary
    assert resp.race_predictions == {"5.0": 990, "10.0": 2100}
