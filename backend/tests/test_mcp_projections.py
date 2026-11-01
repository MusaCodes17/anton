"""LLM brief projections for MCP read payloads (R14 T1).

The brief projections are deliberately smaller than the REST schemas. These tests
pin three rules: the exact key set, the formatting boundaries (nickname, rounding,
missing pace/HR, exact percentage), and that no brief value disagrees with the full
REST-shaped payload it is a projection of.
"""
from datetime import date

from app.models.models import OwnedShoe, ShoeRun
from app.services import rotation
from app.utils.activity_tags import ACTIVITY_TAGS
from app.mcp_server._shared import (
    _owned_shoe_brief,
    _owned_shoes_payload,
    _pct_of_limit,
    _shoe_run_brief,
    _shoe_run_payload,
)

OWNED_BRIEF_KEYS = {"id", "name", "shoe_type", "status", "current_mileage_km",
                    "mileage_limit_km", "pct_of_limit", "total_runs"}
RUN_BRIEF_KEYS = {"run_id", "date", "distance_km", "avg_pace", "avg_hr", "activity_tag", "source"}


def _shoe(db, *, nickname=None, current=10.0, limit=None, shoe_type="daily"):
    shoe = OwnedShoe(brand="Nike", model="Pegasus", shoe_type=shoe_type, starting_mileage=current,
                     current_mileage=current, mileage_limit=limit, nickname=nickname)
    db.add(shoe)
    db.commit()
    db.refresh(shoe)
    return shoe


def _run(db, shoe, *, distance_km=12.0, avg_pace=None, avg_hr=None, activity_tag=None, source="manual"):
    result = rotation.log_run(db, shoe.id, distance_km=distance_km, run_date=date(2026, 7, 1),
                              avg_pace=avg_pace, avg_hr=avg_hr, activity_tag=activity_tag, source=source)
    return result.run


# --- 1. exact key sets -------------------------------------------------------

def test_owned_brief_has_exactly_the_brief_keys(db):
    shoe = _shoe(db, limit=400.0)
    rotation.attach_computed_fields_bulk(db, [shoe])
    assert set(_owned_shoe_brief(shoe)) == OWNED_BRIEF_KEYS


def test_run_brief_has_exactly_the_brief_keys(db):
    shoe = _shoe(db)
    run = _run(db, shoe)
    assert set(_shoe_run_brief(run)) == RUN_BRIEF_KEYS


# --- 2. name formatting ------------------------------------------------------

def test_name_without_nickname_is_brand_and_model(db):
    shoe = _shoe(db)
    rotation.attach_computed_fields_bulk(db, [shoe])
    assert _owned_shoe_brief(shoe)["name"] == "Nike Pegasus"


def test_name_with_nickname_appends_it_in_parens(db):
    shoe = _shoe(db, nickname="Race day")
    rotation.attach_computed_fields_bulk(db, [shoe])
    assert _owned_shoe_brief(shoe)["name"] == "Nike Pegasus (Race day)"


def test_empty_nickname_is_treated_as_no_nickname(db):
    # Same rule as the shoe resources: an empty string adds no parens.
    shoe = _shoe(db, nickname="")
    rotation.attach_computed_fields_bulk(db, [shoe])
    assert _owned_shoe_brief(shoe)["name"] == "Nike Pegasus"


# --- 3. pct_of_limit ---------------------------------------------------------

def test_pct_of_limit_is_none_without_a_limit():
    assert _pct_of_limit(300.0, None) is None


def test_pct_of_limit_is_none_for_a_zero_limit():
    # Falsy limit is "no limit", matching the resource's `if mileage_limit` guard.
    assert _pct_of_limit(300.0, 0) is None


def test_pct_of_limit_exact_value():
    assert _pct_of_limit(300.0, 400.0) == 75


def test_pct_of_limit_is_rounded_to_whole_percent():
    assert _pct_of_limit(100.0, 300.0) == 33


def test_owned_brief_pct_uses_the_limit(db):
    shoe = _shoe(db, current=300.0, limit=400.0)
    rotation.attach_computed_fields_bulk(db, [shoe])
    assert _owned_shoe_brief(shoe)["pct_of_limit"] == 75
    assert _owned_shoe_brief(shoe)["mileage_limit_km"] == 400.0


def test_owned_brief_pct_is_none_without_limit(db):
    shoe = _shoe(db, current=300.0, limit=None)
    rotation.attach_computed_fields_bulk(db, [shoe])
    brief = _owned_shoe_brief(shoe)
    assert brief["pct_of_limit"] is None and brief["mileage_limit_km"] is None


# --- 4. current_mileage_km rounding -----------------------------------------

def test_current_mileage_km_is_rounded_to_one_decimal(db):
    shoe = _shoe(db, current=123.456)
    rotation.attach_computed_fields_bulk(db, [shoe])
    assert _owned_shoe_brief(shoe)["current_mileage_km"] == 123.5


# --- 5. run brief with missing pace/HR ---------------------------------------

def test_run_brief_missing_pace_and_hr_are_none_not_a_crash(db):
    shoe = _shoe(db)
    run = _run(db, shoe, avg_pace=None, avg_hr=None)
    brief = _shoe_run_brief(run)
    assert brief["avg_pace"] is None
    assert brief["avg_hr"] is None


def test_run_brief_date_is_an_iso_string(db):
    shoe = _shoe(db)
    run = _run(db, shoe)
    assert _shoe_run_brief(run)["date"] == "2026-07-01"


def test_run_brief_pace_formats_as_display_string(db):
    shoe = _shoe(db)
    run = _run(db, shoe, avg_pace="5:00/km", avg_hr=150)
    brief = _shoe_run_brief(run)
    assert brief["avg_pace"] == "5:00/km" and brief["avg_hr"] == 150


# --- 6. run_id is the ShoeRun id ---------------------------------------------

def test_run_brief_run_id_is_the_shoe_run_id(db):
    shoe = _shoe(db)
    run = _run(db, shoe)
    assert _shoe_run_brief(run)["run_id"] == run.id
    assert db.query(ShoeRun).get(run.id) is run


# --- 7. briefs never invent data: values agree with the full payloads --------

def test_owned_brief_values_match_full_payload(db):
    shoe = _shoe(db, nickname="Race day", current=300.0, limit=400.0, shoe_type="race")
    _run(db, shoe, distance_km=12.0)
    full = _owned_shoes_payload(db, [shoe])[0]
    brief = _owned_shoe_brief(shoe)
    # Direct counterparts in the REST-shaped payload.
    assert brief["id"] == full["id"]
    assert brief["shoe_type"] == full["shoe_type"]
    assert brief["status"] == full["status"]
    assert brief["total_runs"] == full["total_runs"]
    assert brief["mileage_limit_km"] == full["mileage_limit"]
    # Derived counterpart: the brief rounds current_mileage to one decimal.
    assert brief["current_mileage_km"] == round(full["current_mileage"], 1)
    # `name`, `pct_of_limit` have no full counterpart (display and derived values).


def test_run_brief_values_match_full_payload(db):
    shoe = _shoe(db)
    run = _run(db, shoe, distance_km=12.5, avg_pace="5:00/km", avg_hr=150, source="manual")
    full = _shoe_run_payload(run)
    brief = _shoe_run_brief(run)
    assert brief["run_id"] == full["id"]
    assert brief["date"] == full["run_date"]
    assert brief["distance_km"] == full["distance_km"]
    assert brief["avg_pace"] == full["avg_pace"]
    assert brief["avg_hr"] == full["avg_hr"]
    assert brief["source"] == full["source"]
    # `activity_tag` has no full counterpart in ShoeRunResponse; it is brief-only.


def test_run_brief_activity_tag_passes_through_vocabulary_value(db):
    shoe = _shoe(db)
    tag = ACTIVITY_TAGS[0]
    run = _run(db, shoe, activity_tag=tag)
    assert _shoe_run_brief(run)["activity_tag"] == tag
