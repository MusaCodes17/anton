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


def test_shoe_run_response_allows_zero_distance():
    """Historical COROS runs logged at 0km (mileage already counted manually)
    must still serialize in responses, else GET /runs 500s for that shoe."""
    from datetime import datetime
    from app.models.schemas import ShoeRunResponse

    r = ShoeRunResponse(
        distance_km=0.0,
        run_date=date(2026, 6, 18),
        avg_pace="4:28/km",
        avg_hr=155,
        notes="Actual distance 11.06 km — logged at 0km since mileage was already added manually.",
        id=11,
        owned_shoe_id=9,
        source="coros",
        created_at=datetime(2026, 6, 18, 12, 0, 0),
    )
    assert r.distance_km == 0.0


def test_shoe_run_create_still_rejects_zero_distance():
    """Manual logging stays strict: a 0km run makes no sense to create."""
    import pytest
    from app.models.schemas import ShoeRunCreate

    with pytest.raises(Exception):
        ShoeRunCreate(distance_km=0.0, run_date=date(2026, 6, 18))


def test_log_run_persists_rich_fields(db):
    """F1: rich COROS fields written through log_run land on the Activity row."""
    shoe = _make_shoe(db, 0.0)
    result = rotation.log_run(
        db,
        shoe.id,
        distance_km=12.3,
        run_date=date(2026, 7, 8),
        name="Tempo 10k",
        elevation_gain_m=45.5,
        moving_time_s=2940,
        elapsed_time_s=3060,
        avg_cadence=178.0,
        calories=610.0,
        training_load=87.5,
        training_focus="Aerobic base",
        activity_tag="Tempo",
    )
    act = result.activity
    assert act.name == "Tempo 10k"
    assert act.elevation_gain_m == pytest.approx(45.5)
    assert act.moving_time_s == 2940
    assert act.elapsed_time_s == 3060
    assert act.avg_cadence == pytest.approx(178.0)
    assert act.calories == pytest.approx(610.0)
    assert act.training_load == pytest.approx(87.5)
    assert act.training_focus == "Aerobic base"
    assert act.activity_tag == "Tempo"
