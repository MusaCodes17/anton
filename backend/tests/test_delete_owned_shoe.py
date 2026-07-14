"""
Tests for D1: rotation.delete_owned_shoe — sanctioned shoe deletion path.

Verifies:
  - ShoeRun + ShoeNote are cascade-deleted (ORM relationship)
  - Non-strava Activities are deleted with their runs
  - Strava Activities survive (INV-4: archive is sacred)
  - PlannedRace.planned_shoe_id is NULLed, not the race deleted
  - StravaGearMapping.owned_shoe_id is NULLed, not the mapping deleted
  - CheckpointPrompt records (NOT NULL FK) are deleted
  - LookupError on missing shoe
"""
import pytest
from datetime import date

from app.models.models import (
    Activity, CheckpointPrompt, OwnedShoe, PlannedRace,
    ShoeNote, ShoeRun, StravaGearMapping,
)
from app.services import rotation


def _shoe(db, **kw) -> OwnedShoe:
    shoe = OwnedShoe(brand="Test", model="Model", starting_mileage=0.0,
                     current_mileage=0.0, **kw)
    db.add(shoe)
    db.commit()
    db.refresh(shoe)
    return shoe


def _activity(db, source="manual", distance_km=10.0) -> Activity:
    act = Activity(source=source, run_date=date(2026, 1, 1),
                   distance_km=distance_km, moving_time_s=3600)
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


def _run(db, shoe, activity) -> ShoeRun:
    run = ShoeRun(owned_shoe_id=shoe.id, activity_id=activity.id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def test_delete_owned_shoe_removes_shoe(db):
    shoe = _shoe(db)
    rotation.delete_owned_shoe(db, shoe.id)
    assert db.query(OwnedShoe).filter(OwnedShoe.id == shoe.id).first() is None


def test_delete_owned_shoe_cascades_shoe_note(db):
    shoe = _shoe(db)
    note = ShoeNote(owned_shoe_id=shoe.id, body="test note", mileage_at_note=0.0)
    db.add(note)
    db.commit()

    rotation.delete_owned_shoe(db, shoe.id)
    assert db.query(ShoeNote).filter(ShoeNote.owned_shoe_id == shoe.id).count() == 0


def test_delete_owned_shoe_deletes_manual_activity(db):
    shoe = _shoe(db)
    act = _activity(db, source="manual")
    _run(db, shoe, act)

    rotation.delete_owned_shoe(db, shoe.id)
    assert db.query(Activity).filter(Activity.id == act.id).first() is None


def test_delete_owned_shoe_deletes_coros_activity(db):
    shoe = _shoe(db)
    act = _activity(db, source="coros")
    _run(db, shoe, act)

    rotation.delete_owned_shoe(db, shoe.id)
    assert db.query(Activity).filter(Activity.id == act.id).first() is None


def test_delete_owned_shoe_preserves_strava_activity(db):
    """INV-4: strava archive rows must survive shoe deletion."""
    shoe = _shoe(db)
    act = _activity(db, source="strava")
    _run(db, shoe, act)

    rotation.delete_owned_shoe(db, shoe.id)
    # Activity survives; ShoeRun is gone (cascade)
    assert db.query(Activity).filter(Activity.id == act.id).first() is not None
    assert db.query(ShoeRun).filter(ShoeRun.owned_shoe_id == shoe.id).count() == 0


def test_delete_owned_shoe_nulls_planned_race_ref(db):
    shoe = _shoe(db)
    race = PlannedRace(name="Test 5K", race_date=date(2026, 6, 1),
                       planned_shoe_id=shoe.id)
    db.add(race)
    db.commit()

    rotation.delete_owned_shoe(db, shoe.id)
    db.refresh(race)
    assert race.planned_shoe_id is None      # ref nulled, race preserved


def test_delete_owned_shoe_nulls_strava_gear_mapping(db):
    shoe = _shoe(db)
    mapping = StravaGearMapping(gear_name="Vaporfly 3", owned_shoe_id=shoe.id)
    db.add(mapping)
    db.commit()

    rotation.delete_owned_shoe(db, shoe.id)
    db.refresh(mapping)
    assert mapping.owned_shoe_id is None     # ref nulled, mapping preserved


def test_delete_owned_shoe_removes_checkpoint_prompts(db):
    shoe = _shoe(db)
    cp = CheckpointPrompt(owned_shoe_id=shoe.id, checkpoint_km=100)
    db.add(cp)
    db.commit()

    rotation.delete_owned_shoe(db, shoe.id)
    assert db.query(CheckpointPrompt).filter(
        CheckpointPrompt.owned_shoe_id == shoe.id
    ).count() == 0


def test_delete_owned_shoe_raises_on_missing(db):
    with pytest.raises(LookupError):
        rotation.delete_owned_shoe(db, 99999)


def test_delete_owned_shoe_does_not_touch_other_shoes(db):
    """Deleting one shoe must not disturb another shoe's data."""
    shoe_a = _shoe(db)
    shoe_b = _shoe(db)
    act_b = _activity(db, source="manual")
    _run(db, shoe_b, act_b)

    rotation.delete_owned_shoe(db, shoe_a.id)
    assert db.query(OwnedShoe).filter(OwnedShoe.id == shoe_b.id).first() is not None
    assert db.query(Activity).filter(Activity.id == act_b.id).first() is not None
