"""
Tests for the R2.4 shoe-type controlled vocabulary: the backend-owned list, the
`GET /api/shoe-types` endpoint, and the write-schema validation that rejects
off-vocabulary values (the typo that used to fail silently at the cross-domain
join). Exercised at the service/schema level to match the suite's style.
"""
import pytest
from pydantic import ValidationError

from app.models.schemas import (
    OwnedShoeCreate, OwnedShoeUpdate, ShoeCreate, ShoeUpdate,
)
from app.routers.shoe_types import get_shoe_types
from app.utils.shoe_types import SHOE_TYPES, is_valid_shoe_type


def test_vocabulary_membership():
    assert is_valid_shoe_type("long_distance_racer") is True
    assert is_valid_shoe_type("daily_trainer") is True
    assert is_valid_shoe_type("Daily Trainer") is False   # legacy free-text
    assert is_valid_shoe_type("racing_flat") is False      # not in vocab
    assert is_valid_shoe_type(None) is False               # None handled by callers


def test_endpoint_serves_the_ordered_vocabulary():
    served = get_shoe_types()
    assert served == list(SHOE_TYPES)
    assert served[0] == "long_distance_racer"              # order is display order
    assert len(served) == len(set(served))                 # no dupes


@pytest.mark.parametrize("schema", [ShoeCreate, OwnedShoeCreate])
def test_create_schemas_accept_valid_and_clear_empty(schema):
    ok = schema(brand="Nike", model="Vaporfly", shoe_type="tempo")
    assert ok.shoe_type == "tempo"
    # None and "" both clear to None (a shoe may be untyped)
    assert schema(brand="Nike", model="Pegasus", shoe_type=None).shoe_type is None
    assert schema(brand="Nike", model="Pegasus", shoe_type="").shoe_type is None
    # omitted entirely → None
    assert schema(brand="Nike", model="Pegasus").shoe_type is None


@pytest.mark.parametrize("schema", [ShoeCreate, OwnedShoeCreate])
def test_create_schemas_reject_off_vocabulary(schema):
    with pytest.raises(ValidationError) as exc:
        schema(brand="Nike", model="Streakfly", shoe_type="Race Shoe")
    assert "Invalid shoe_type" in str(exc.value)


@pytest.mark.parametrize("schema", [ShoeUpdate, OwnedShoeUpdate])
def test_update_schemas_validate_shoe_type(schema):
    assert schema(shoe_type="recovery").shoe_type == "recovery"
    assert schema(shoe_type=None).shoe_type is None
    # a partial update that omits shoe_type entirely is fine (stays unset)
    assert schema(nickname="x").shoe_type is None
    with pytest.raises(ValidationError):
        schema(shoe_type="tempo_shoe")   # close-but-wrong typo is caught
