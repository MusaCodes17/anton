"""Tests for R2.7 T5 + F3 — athlete fitness snapshots (append-only, latest wins)."""
from app.routers.training import get_fitness
from app.services import fitness as fitness_svc


def test_latest_is_none_when_empty(db):
    assert fitness_svc.latest(db) is None
    resp = get_fitness(db=db)
    assert resp.has_data is False
    assert resp.vo2max is None
    assert resp.running_level is None


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


def test_running_level_round_trips(db):
    """F3: running_level persists through service and surfaces in the endpoint response."""
    fitness_svc.record_snapshot(db, vo2max=61.0, running_level=74.5,
                                threshold_pace_s_per_km=220,
                                race_predictions={"5.0": 1005})
    resp = get_fitness(db=db)
    assert resp.has_data is True
    assert resp.running_level == 74.5


def test_running_level_absent_stays_none(db):
    """Empty envelope remains has_data=False when no snapshot exists;
    running_level is None when not provided."""
    snap = fitness_svc.record_snapshot(db, vo2max=60.0)
    assert snap.running_level is None
    resp = get_fitness(db=db)
    assert resp.has_data is True
    assert resp.running_level is None


# --- R8.4.1: automatic snapshots are saved only when the reading changed ----------

PRED = {"5.0": 977, "10.0": 2007, "21.0975": 4349, "42.195": 8864}


def test_record_if_changed_saves_first_then_skips_repeats(db):
    first = fitness_svc.record_if_changed(db, vo2max=59.0, running_level=97.0,
                                          threshold_pace_s_per_km=204, race_predictions=PRED)
    assert first is not None
    again = fitness_svc.record_if_changed(db, vo2max=59, running_level=97,     # ints == floats
                                          threshold_pace_s_per_km=204, race_predictions=dict(PRED))
    assert again is None
    assert fitness_svc.latest(db).id == first.id


def test_record_if_changed_saves_any_single_change(db):
    fitness_svc.record_if_changed(db, vo2max=59.0, running_level=97.0,
                                  threshold_pace_s_per_km=204, race_predictions=PRED)
    changed = fitness_svc.record_if_changed(db, vo2max=59.0, running_level=97.0, threshold_pace_s_per_km=204,
                                            race_predictions={**PRED, "42.195": 8850})
    assert changed is not None and fitness_svc.latest(db).race_predictions["42.195"] == 8850


def test_record_if_changed_ignores_an_empty_reading(db):
    assert fitness_svc.record_if_changed(db) is None
    assert fitness_svc.record_if_changed(db, race_predictions={}) is None
    assert fitness_svc.latest(db) is None


def test_a_dropped_metric_is_a_change_stored_as_none(db):
    fitness_svc.record_if_changed(db, vo2max=59.0, running_level=97.0)
    snap = fitness_svc.record_if_changed(db, vo2max=59.0)
    assert snap is not None and snap.running_level is None
