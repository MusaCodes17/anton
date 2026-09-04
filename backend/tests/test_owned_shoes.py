"""
Regression tests for the owned-shoe mileage-ledger boundary (C1 fix, 2026-07-07).

INV-1: `current_mileage = starting_mileage + Σ attributed distances`, maintained
only through the sanctioned paths (rotation.log_run / delete_run / adjust_mileage).
The generic PUT /owned-shoes/{id} must NOT be able to overwrite the ledger — this
module pins that the update schema drops current_mileage / starting_mileage, and
that rotation.adjust_mileage is the one door that sets current_mileage directly.
"""
from app.models import OwnedShoeUpdate
from app.models.models import OwnedShoe, ShoeNote
from app.routers.owned_shoes import update_owned_shoe
from app.services import rotation


def _make_shoe(db, current_mileage: float) -> OwnedShoe:
    shoe = OwnedShoe(
        brand="Test",
        model="Shoe",
        starting_mileage=current_mileage,
        current_mileage=current_mileage,
    )
    db.add(shoe)
    db.commit()
    db.refresh(shoe)
    return shoe


def test_put_ignores_current_mileage(db):
    """A PUT carrying current_mileage must leave the ledger untouched (C1)."""
    shoe = _make_shoe(db, 100.0)
    # A client attempts to overwrite the ledger through the generic update path.
    update = OwnedShoeUpdate.model_validate({"current_mileage": 999.0, "nickname": "Racer"})

    update_owned_shoe(shoe.id, update, db)
    db.refresh(shoe)

    assert shoe.current_mileage == 100.0  # ledger untouched
    assert shoe.nickname == "Racer"        # other fields still applied


def test_put_ignores_starting_mileage(db):
    """starting_mileage is the ledger anchor — not settable via the generic PUT."""
    shoe = _make_shoe(db, 100.0)
    update = OwnedShoeUpdate.model_validate({"starting_mileage": 5.0})

    update_owned_shoe(shoe.id, update, db)
    db.refresh(shoe)

    assert shoe.starting_mileage == 100.0


def test_adjust_mileage_sets_value_and_records_note(db):
    """The sanctioned override sets current_mileage and journals the change."""
    shoe = _make_shoe(db, 100.0)

    updated = rotation.adjust_mileage(db, shoe.id, 250.0)

    assert updated.current_mileage == 250.0
    notes = db.query(ShoeNote).filter(ShoeNote.owned_shoe_id == shoe.id).all()
    assert len(notes) == 1
    assert notes[0].triggered_by == "mileage_adjustment"
    assert notes[0].mileage_at_note == 250.0


def test_adjust_mileage_missing_shoe_raises(db):
    import pytest
    with pytest.raises(LookupError):
        rotation.adjust_mileage(db, 9999, 100.0)


# --- T3: owned-shoe status vocabulary validation (write-time 422) ---

def test_create_rejects_off_vocab_status():
    """An unknown status is a 422 at the write schema, not silently persisted."""
    import pytest
    from pydantic import ValidationError
    from app.models import OwnedShoeCreate
    with pytest.raises(ValidationError):
        OwnedShoeCreate.model_validate(
            {"brand": "Nike", "model": "Vaporfly", "status": "sold"}
        )


def test_create_accepts_every_vocab_status():
    """Each member of the vocabulary validates and round-trips."""
    from app.models import OwnedShoeCreate
    from app.models.schemas import OWNED_SHOE_STATUSES
    for status in OWNED_SHOE_STATUSES:
        obj = OwnedShoeCreate.model_validate(
            {"brand": "Nike", "model": "Vaporfly", "status": status}
        )
        assert obj.status == status


def test_update_rejects_off_vocab_status():
    """The update path validates status too."""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        OwnedShoeUpdate.model_validate({"status": "bogus"})


def test_update_allows_omitted_status():
    """None means 'unchanged' on update — must not be rejected."""
    update = OwnedShoeUpdate.model_validate({"nickname": "x"})
    assert update.status is None


# --- #8: mileage_limit defaults by shoe_type ---

def test_default_mileage_limit_map():
    """The product-rule map + fallback (utils/shoe_types)."""
    from app.utils.shoe_types import default_mileage_limit
    assert default_mileage_limit("long_distance_racer") == 450.0
    assert default_mileage_limit("tempo") == 500.0
    assert default_mileage_limit("daily_trainer") == 700.0
    assert default_mileage_limit("trail") == 600.0
    assert default_mileage_limit(None) == 600.0          # fallback
    assert default_mileage_limit("not_a_real_type") == 600.0  # fallback


def test_create_defaults_mileage_limit_by_type(db):
    """A freshly created shoe with no mileage_limit gets the type default (#8),
    so it can enter the retirement pipeline instead of being NULL-excluded."""
    from app.models import OwnedShoeCreate
    from app.routers.owned_shoes import create_owned_shoe

    created = create_owned_shoe(
        OwnedShoeCreate.model_validate(
            {"brand": "Adidas", "model": "Adios Pro 3", "shoe_type": "long_distance_racer"}
        ),
        db,
    )
    assert created.mileage_limit == 450.0


def test_create_respects_explicit_mileage_limit(db):
    """An explicit mileage_limit is never overridden by the default."""
    from app.models import OwnedShoeCreate
    from app.routers.owned_shoes import create_owned_shoe

    created = create_owned_shoe(
        OwnedShoeCreate.model_validate(
            {"brand": "Nike", "model": "Pegasus", "shoe_type": "daily_trainer",
             "mileage_limit": 900.0}
        ),
        db,
    )
    assert created.mileage_limit == 900.0


def test_defaulted_limit_puts_worn_shoe_in_retirement_pipeline(db):
    """End-to-end: a shoe created past 75% of its now-defaulted limit surfaces in
    rotation.retirement_pipeline (the Home shoe-health alert's source)."""
    from app.models import OwnedShoeCreate
    from app.routers.owned_shoes import create_owned_shoe

    # tempo default = 500 → 75% = 375. Seed it already worn past that.
    created = create_owned_shoe(
        OwnedShoeCreate.model_validate(
            {"brand": "Saucony", "model": "Endorphin", "shoe_type": "tempo",
             "starting_mileage": 400.0}
        ),
        db,
    )
    assert created.mileage_limit == 500.0
    assert created.current_mileage == 400.0  # starts at starting_mileage

    pipeline = rotation.retirement_pipeline(db)
    assert any(e.shoe.id == created.id for e in pipeline)
