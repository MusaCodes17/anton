"""
Regression tests for rotation.log_run — checkpoint detection and RunLogResult shape.
Covers the T1 fix: mcp_server.log_run_to_shoe previously referenced undefined
`checkpoint_reached` / `new_checkpoint` names; these tests verify the underlying
service returns the correct attributes.
"""
from datetime import date

import pytest

from app.models.models import OwnedShoe
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


def test_log_run_no_checkpoint(db):
    shoe = _make_shoe(db, 50.0)
    result = rotation.log_run(db, shoe.id, distance_km=10.0, run_date=date(2026, 7, 1))
    assert result.checkpoint_reached is False
    assert result.checkpoint_km is None
    assert result.shoe.current_mileage == pytest.approx(60.0)


def test_log_run_crosses_checkpoint(db):
    shoe = _make_shoe(db, 95.0)
    result = rotation.log_run(db, shoe.id, distance_km=10.0, run_date=date(2026, 7, 1))
    assert result.checkpoint_reached is True
    assert result.checkpoint_km == 100


def test_log_run_result_has_run_and_shoe(db):
    shoe = _make_shoe(db, 0.0)
    result = rotation.log_run(db, shoe.id, distance_km=5.0, run_date=date(2026, 7, 1))
    assert result.run.id is not None
    assert result.shoe.id == shoe.id
