"""
Editable retirement limit: the runner's own mileage_limit vs the derived
type-default recommendation. The limit is a heuristic the runner may override;
the recommendation stays visible and is never stored (INV-7).
"""
import pytest

from app.models import OwnedShoeUpdate
from app.models.models import OwnedShoe
from app.routers.owned_shoes import update_owned_shoe
from app.services import rotation


def _shoe(db, *, shoe_type="daily_trainer", limit=700.0, current=0.0) -> OwnedShoe:
    s = OwnedShoe(brand="Test", model="Shoe", shoe_type=shoe_type,
                  starting_mileage=current, current_mileage=current, mileage_limit=limit)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_raising_limit_keeps_ledger_and_recommendation(db):
    shoe = _shoe(db, current=700.0)
    out = rotation.set_mileage_limit(db, shoe.id, 900.0)
    assert out.mileage_limit == 900.0
    assert out.current_mileage == 700.0  # ledger untouched (INV-1)
    rotation.attach_computed_fields(db, out)
    assert out.recommended_limit_km == 700.0  # derived from type, not from the edit


def test_raised_limit_drops_shoe_out_of_pipeline(db):
    shoe = _shoe(db, current=700.0)
    assert [e.shoe.id for e in rotation.retirement_pipeline(db)] == [shoe.id]
    rotation.set_mileage_limit(db, shoe.id, 1000.0)  # 70% < 75% threshold
    assert rotation.retirement_pipeline(db) == []


def test_none_resets_to_type_default(db):
    shoe = _shoe(db, shoe_type="long_distance_racer", limit=900.0)
    assert rotation.set_mileage_limit(db, shoe.id, None).mileage_limit == 450.0


@pytest.mark.parametrize("bad", [0, -5])
def test_non_positive_limit_rejected(db, bad):
    shoe = _shoe(db)
    with pytest.raises(ValueError):
        rotation.set_mileage_limit(db, shoe.id, bad)


def test_missing_shoe_raises_lookup(db):
    with pytest.raises(LookupError):
        rotation.set_mileage_limit(db, 9999, 800.0)


def test_put_null_limit_resets_not_clears(db):
    shoe = _shoe(db, shoe_type="tempo", limit=900.0)
    update_owned_shoe(shoe.id, OwnedShoeUpdate.model_validate({"mileage_limit": None}), db)
    db.refresh(shoe)
    assert shoe.mileage_limit == 500.0
