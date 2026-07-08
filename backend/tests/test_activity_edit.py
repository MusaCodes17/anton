"""Tests for R2.7 T6 — activity edit, shoe reassignment (INV-1), race promotion."""
from datetime import date

import pytest

from app.models.models import Activity, OwnedShoe, PlannedRace, ShoeRun
from app.services import activities as activities_svc
from app.services import races as races_svc
from app.services import rotation


def _shoe(db, mileage=0.0, model="Shoe"):
    s = OwnedShoe(brand="Nike", model=model, starting_mileage=mileage, current_mileage=mileage)
    db.add(s); db.commit(); db.refresh(s)
    return s


def test_update_activity_partial(db):
    a = Activity(source="manual", activity_type="Run", run_date=date(2026, 7, 1),
                 distance_km=10.0, name="Morning", activity_tag=None)
    db.add(a); db.commit(); db.refresh(a)

    activities_svc.update_activity(db, a.id, activity_tag="Tempo")
    db.refresh(a)
    assert a.activity_tag == "Tempo"
    assert a.name == "Morning"   # untouched — not supplied

    activities_svc.update_activity(db, a.id, name="Evening", description="notes")
    db.refresh(a)
    assert a.name == "Evening" and a.description == "notes"
    assert a.activity_tag == "Tempo"  # still untouched


def test_reassign_moves_mileage_between_shoes(db):
    old = _shoe(db, model="Old")
    new = _shoe(db, model="New")
    res = rotation.log_run(db, old.id, distance_km=12.0, run_date=date(2026, 7, 2), source="manual")
    activity_id = res.activity.id
    assert db.query(OwnedShoe).get(old.id).current_mileage == pytest.approx(12.0)

    rotation.reassign_attribution(db, activity_id, new.id)
    # Ledger moved wholesale (INV-1): old back to 0, new to 12.
    assert db.query(OwnedShoe).get(old.id).current_mileage == pytest.approx(0.0)
    assert db.query(OwnedShoe).get(new.id).current_mileage == pytest.approx(12.0)
    # Exactly one attribution, now pointing at the new shoe (INV-3 preserved).
    attrs = db.query(ShoeRun).filter(ShoeRun.activity_id == activity_id).all()
    assert len(attrs) == 1 and attrs[0].owned_shoe_id == new.id
    # The Activity row itself survives.
    assert db.query(Activity).get(activity_id) is not None


def test_reassign_same_shoe_is_noop(db):
    shoe = _shoe(db)
    res = rotation.log_run(db, shoe.id, distance_km=5.0, run_date=date(2026, 7, 3), source="manual")
    rotation.reassign_attribution(db, res.activity.id, shoe.id)
    assert db.query(OwnedShoe).get(shoe.id).current_mileage == pytest.approx(5.0)  # not double-counted
    assert db.query(ShoeRun).filter(ShoeRun.activity_id == res.activity.id).count() == 1


def test_reassign_unattributed_activity(db):
    shoe = _shoe(db)
    a = Activity(source="strava", activity_type="Run", run_date=date(2026, 7, 4), distance_km=8.0)
    db.add(a); db.commit(); db.refresh(a)
    rotation.reassign_attribution(db, a.id, shoe.id)
    assert db.query(OwnedShoe).get(shoe.id).current_mileage == pytest.approx(8.0)
    assert db.query(ShoeRun).filter(ShoeRun.activity_id == a.id).count() == 1


def test_promote_activity_to_completed_race(db):
    a = Activity(source="strava", activity_type="Run", run_date=date(2026, 5, 4),
                 distance_km=21.0975, moving_time_s=4620, name="Half Marathon", activity_tag="Race")
    db.add(a); db.commit(); db.refresh(a)

    race = races_svc.create_completed_from_activity(db, a.id)
    assert race.status == "completed"
    assert race.race_date == date(2026, 5, 4)
    assert race.distance_km == pytest.approx(21.0975)
    assert race.result_time_s == 4620
    assert race.name == "Half Marathon"
    assert db.query(PlannedRace).count() == 1


def test_promote_requires_distance(db):
    a = Activity(source="manual", activity_type="Run", run_date=date(2026, 5, 5), distance_km=None)
    db.add(a); db.commit(); db.refresh(a)
    with pytest.raises(ValueError):
        races_svc.create_completed_from_activity(db, a.id)
