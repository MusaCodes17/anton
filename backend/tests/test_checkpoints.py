"""
Tests for R2.6 checkpoint-prompt persistence (services/checkpoints).

The rules:
  1. mark_prompted then list returns the (shoe, km) pair.
  2. mark_prompted is idempotent on the unique (shoe, km) pair — a repeat is a
     silent no-op, not a duplicate row and not an error.
  3. different checkpoints for the same shoe are distinct rows.
"""
from app.models.models import OwnedShoe
from app.services import checkpoints


def _shoe(db, brand="Nike", model="Pegasus"):
    s = OwnedShoe(brand=brand, model=model)
    db.add(s)
    db.flush()
    return s


def test_mark_then_list(db):
    shoe = _shoe(db)
    checkpoints.mark_prompted(db, owned_shoe_id=shoe.id, checkpoint_km=100)
    prompted = checkpoints.list_prompted(db)
    assert prompted == [{"owned_shoe_id": shoe.id, "checkpoint_km": 100}]


def test_mark_is_idempotent(db):
    shoe = _shoe(db)
    first = checkpoints.mark_prompted(db, owned_shoe_id=shoe.id, checkpoint_km=100)
    second = checkpoints.mark_prompted(db, owned_shoe_id=shoe.id, checkpoint_km=100)
    assert first.id == second.id
    assert len(checkpoints.list_prompted(db)) == 1


def test_distinct_checkpoints_same_shoe(db):
    shoe = _shoe(db)
    checkpoints.mark_prompted(db, owned_shoe_id=shoe.id, checkpoint_km=100)
    checkpoints.mark_prompted(db, owned_shoe_id=shoe.id, checkpoint_km=200)
    kms = sorted(p["checkpoint_km"] for p in checkpoints.list_prompted(db))
    assert kms == [100, 200]
