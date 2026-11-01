"""LLM brief projections for MCP read payloads (R14 T1).

The brief projections are deliberately smaller than the REST schemas. These tests
pin three rules: the exact key set, the formatting boundaries (nickname, rounding,
missing pace/HR, exact percentage), and that no brief value disagrees with the full
REST-shaped payload it is a projection of.
"""
from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from sqlalchemy import event

from app import mcp_server
from app.models.models import OwnedShoe, ShoeRun
from app.models.schemas import ShoeRunResponse
from app.routers import owned_shoes as owned_shoes_router
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


@pytest.fixture()
def mcp_db(db, monkeypatch):
    # Same pattern as test_mcp_parity.py: patch _core.get_session, the name the tools use.
    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)
    return db


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


# --- 8. get_owned_shoes tool: brief by default, detail=True for the full record

def test_get_owned_shoes_default_rows_have_exactly_the_brief_keys(mcp_db):
    _shoe(mcp_db)
    rows = mcp_server.get_owned_shoes()
    assert rows and all(set(r) == OWNED_BRIEF_KEYS for r in rows)


def test_get_owned_shoes_detail_rows_keep_the_full_record(mcp_db):
    _shoe(mcp_db)
    rows = mcp_server.get_owned_shoes(detail=True)
    assert rows and "purchase_price" in rows[0] and "cost_per_km" in rows[0]


def test_get_owned_shoes_status_filter_in_both_modes(mcp_db):
    active = _shoe(mcp_db)
    retired = _shoe(mcp_db)
    retired.status = "retired"
    mcp_db.commit()
    for detail in (False, True):
        ids_all = {r["id"] for r in mcp_server.get_owned_shoes(detail=detail)}
        ids_active = {r["id"] for r in mcp_server.get_owned_shoes(status_filter="active", detail=detail)}
        ids_retired = {r["id"] for r in mcp_server.get_owned_shoes(status_filter="retired", detail=detail)}
        assert {active.id, retired.id} <= ids_all
        assert retired.id not in ids_active and active.id in ids_active
        assert ids_retired == {retired.id}


def test_get_owned_shoes_brief_total_runs_counts_logged_runs(mcp_db):
    shoe = _shoe(mcp_db)
    _run(mcp_db, shoe, distance_km=5.0)
    _run(mcp_db, shoe, distance_km=8.0)
    row = next(r for r in mcp_server.get_owned_shoes() if r["id"] == shoe.id)
    assert row["total_runs"] == 2


# --- 9. get_shoe_runs paging (R14 T3) -----------------------------------------

def _many_runs(db, shoe, n):
    """n runs on distinct dates (so newest-first order is unambiguous); returns nothing."""
    base = date(2025, 1, 1)
    for i in range(n):
        rotation.log_run(db, shoe.id, distance_km=5.0 + i * 0.01, run_date=base + timedelta(days=i),
                         avg_pace="5:00/km", avg_hr=150, commit=False)
    db.commit()


def test_shoe_runs_exactly_limit_runs_returns_all_and_has_more_false(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 5)
    out = mcp_server.get_shoe_runs(shoe.id, limit=5)
    assert len(out["runs"]) == 5 and out["has_more"] is False and out["total_runs"] == 5


def test_shoe_runs_limit_plus_one_runs_returns_limit_and_has_more_true(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 6)
    out = mcp_server.get_shoe_runs(shoe.id, limit=5)
    assert len(out["runs"]) == 5 and out["has_more"] is True and out["total_runs"] == 6


def test_shoe_runs_offset_past_the_end_is_empty_with_correct_total(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 3)
    out = mcp_server.get_shoe_runs(shoe.id, offset=10)
    assert out["runs"] == [] and out["has_more"] is False and out["total_runs"] == 3


def test_shoe_runs_limit_500_clamps_to_200_and_has_more_true_with_201_runs(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 201)
    out = mcp_server.get_shoe_runs(shoe.id, limit=500)
    assert len(out["runs"]) == 200 and out["has_more"] is True and out["total_runs"] == 201


def test_shoe_runs_limit_0_clamps_to_1(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 3)
    out = mcp_server.get_shoe_runs(shoe.id, limit=0)
    assert len(out["runs"]) == 1 and out["has_more"] is True


def test_shoe_runs_negative_offset_clamps_to_0(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 3)
    assert mcp_server.get_shoe_runs(shoe.id, offset=-5)["runs"] == mcp_server.get_shoe_runs(shoe.id, offset=0)["runs"]


def test_shoe_runs_pages_concatenate_newest_first_without_overlap(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 7)
    whole = mcp_server.get_shoe_runs(shoe.id, limit=200)["runs"]
    p1 = mcp_server.get_shoe_runs(shoe.id, limit=4, offset=0)["runs"]
    p2 = mcp_server.get_shoe_runs(shoe.id, limit=4, offset=4)["runs"]
    assert p1 + p2 == whole and len(whole) == 7
    assert len({r["run_id"] for r in p1 + p2}) == 7
    dates = [r["date"] for r in whole]
    assert dates == sorted(dates, reverse=True)


def test_shoe_runs_lifetime_stats_ignore_the_page(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 7)
    stats = rotation.compute_lifetime_stats(mcp_db, shoe.id)
    keys = ("lifetime_avg_pace", "lifetime_avg_hr", "total_runs")
    pages = [mcp_server.get_shoe_runs(shoe.id, limit=3, offset=0),
             mcp_server.get_shoe_runs(shoe.id, limit=3, offset=3),
             mcp_server.get_shoe_runs(shoe.id, limit=200)]
    for out in pages:
        assert {k: out[k] for k in keys} == {"lifetime_avg_pace": stats.lifetime_avg_pace,
                                              "lifetime_avg_hr": stats.lifetime_avg_hr,
                                              "total_runs": stats.total_runs}
    assert stats.total_runs == 7


def test_shoe_runs_default_rows_have_exactly_the_brief_keys(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 2)
    out = mcp_server.get_shoe_runs(shoe.id)
    assert set(out) == {"owned_shoe_id", "runs", "total_runs", "has_more", "lifetime_avg_pace", "lifetime_avg_hr"}
    assert all(set(r) == RUN_BRIEF_KEYS for r in out["runs"])


def test_shoe_runs_detail_true_matches_pre_change_output_regression_lock(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 4)
    _run(mcp_db, shoe, avg_pace="4:50/km", avg_hr=160)
    out = mcp_server.get_shoe_runs(shoe.id, limit=200, detail=True)
    # has_more is the only key added by T3; removing it must leave the pre-change shape exactly.
    out.pop("has_more")
    assert list(out) == ["owned_shoe_id", "runs", "lifetime_avg_pace", "lifetime_avg_hr", "total_runs"]
    stats = rotation.compute_lifetime_stats(mcp_db, shoe.id)
    rest_rows = [ShoeRunResponse.model_validate(r).model_dump(mode="json")
                 for r in owned_shoes_router.get_shoe_runs(shoe.id, db=mcp_db)]
    assert out == {
        "owned_shoe_id": shoe.id,
        "runs": rest_rows,
        "lifetime_avg_pace": stats.lifetime_avg_pace,
        "lifetime_avg_hr": stats.lifetime_avg_hr,
        "total_runs": stats.total_runs,
    }
    assert len(rest_rows) == 5


def test_shoe_runs_query_is_limited_in_sql_not_sliced_in_python(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 8)
    seen = []

    def grab(conn, cursor, statement, parameters, context, executemany):
        if "FROM shoe_runs" in statement and "JOIN activities" in statement:
            seen.append(statement)

    engine = mcp_db.get_bind()
    event.listen(engine, "after_cursor_execute", grab)
    try:
        out = mcp_server.get_shoe_runs(shoe.id, limit=3, offset=2)
    finally:
        event.remove(engine, "after_cursor_execute", grab)
    assert len(out["runs"]) == 3
    runs_stmts = [s for s in seen if "ORDER BY" in s]
    assert runs_stmts, "runs statement not captured"
    assert all("LIMIT" in s and "OFFSET" in s for s in runs_stmts)


# --- 10. lean MCP resources (R14 T4) -----------------------------------------
# The embedded ```json block is the machine-readable half of both resources.

import json as _json

from app.mcp_server.shoes import _RUNS_RESOURCE_CAP, shoe_rotation_resource, shoe_runs_resource


def _embedded_json(text):
    return _json.loads(text.rsplit("```json\n", 1)[1].rsplit("\n```", 1)[0])


def _table_rows(text):
    return [line for line in text.splitlines() if line.startswith("| ") and "km |" in line]


def test_rotation_json_rows_have_exactly_the_brief_keys_and_include_retired(mcp_db):
    _shoe(mcp_db, nickname="Daily")
    retired = _shoe(mcp_db, current=500.0)
    retired.status = "retired"
    mcp_db.commit()
    shoes = _embedded_json(shoe_rotation_resource())["shoes"]
    assert len(shoes) == 2
    assert all(set(row) == OWNED_BRIEF_KEYS for row in shoes)
    assert retired.id in {row["id"] for row in shoes}


def test_rotation_markdown_still_shows_pace_and_run_count_for_active_shoe(mcp_db):
    shoe = _shoe(mcp_db)
    _run(mcp_db, shoe, distance_km=10.0, avg_pace="5:00/km", avg_hr=150)
    text = shoe_rotation_resource()
    assert "Avg pace: 5:00/km" in text
    assert "1 runs" in text
    row = next(r for r in _embedded_json(text)["shoes"] if r["id"] == shoe.id)
    assert row["total_runs"] == 1


def test_runs_resource_at_cap_returns_all_rows_and_no_older_line(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, _RUNS_RESOURCE_CAP)
    text = shoe_runs_resource(shoe.id)
    data = _embedded_json(text)
    assert len(_table_rows(text)) == _RUNS_RESOURCE_CAP
    assert len(data["runs"]) == _RUNS_RESOURCE_CAP
    assert data["total_runs"] == _RUNS_RESOURCE_CAP
    assert f"_{_RUNS_RESOURCE_CAP} runs logged_" in text
    assert "older runs" not in text


def test_runs_resource_over_cap_shows_newest_page_and_offset_footer(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, _RUNS_RESOURCE_CAP + 1)
    text = shoe_runs_resource(shoe.id)
    data = _embedded_json(text)
    assert len(_table_rows(text)) == _RUNS_RESOURCE_CAP
    assert len(data["runs"]) == _RUNS_RESOURCE_CAP
    assert data["total_runs"] == _RUNS_RESOURCE_CAP + 1
    assert f"_{_RUNS_RESOURCE_CAP + 1} runs logged_" in text
    assert "1 older runs" in text
    assert f"offset={_RUNS_RESOURCE_CAP}" in text
    # Newest-first: the 50 kept are the most recent; the oldest run (2025-01-01) is dropped.
    dates = [r["date"] for r in data["runs"]]
    assert dates[0] == "2025-02-20" and dates[-1] == "2025-01-02"
    assert dates == sorted(dates, reverse=True)


def test_runs_resource_json_rows_have_exactly_the_brief_keys(mcp_db):
    shoe = _shoe(mcp_db)
    _many_runs(mcp_db, shoe, 3)
    data = _embedded_json(shoe_runs_resource(shoe.id))
    assert set(data) == {"shoe_id", "runs", "lifetime_avg_pace", "lifetime_avg_hr", "total_runs"}
    assert all(set(r) == RUN_BRIEF_KEYS for r in data["runs"])
