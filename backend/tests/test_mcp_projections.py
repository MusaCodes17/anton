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


# --- 11. get_watchlist brief + paging (R14 T5a) -------------------------------

import asyncio as _asyncio
from datetime import datetime as _datetime

from app.mcp_server.deals import deals_watchlist_resource
from app.models.models import Deal, PriceRecord, Retailer, Shoe
from app.services.chat_service import call_tool_once

WATCHLIST_BRIEF_KEYS = {"shoe_id", "brand", "model", "shoe_type", "msrp", "target_price",
                        "on_sale", "best_deal", "best_ever_price"}
BEST_DEAL_KEYS = {"deal_id", "retailer_name", "current_price", "savings_percent"}


def _wl_shoe(db, model, *, brand="Nike"):
    s = Shoe(brand=brand, model=model, target_price=180.0, msrp=220.0, is_active=True)
    db.add(s)
    db.flush()
    return s


def _wl_retailer(db, name="TLH"):
    r = Retailer(name=name, base_url=f"https://{name.lower()}.example")
    db.add(r)
    db.flush()
    return r


def _wl_on_sale(db, shoe, retailer, *, price=150.0):
    db.add(Deal(shoe_id=shoe.id, retailer_id=retailer.id, current_price=price, target_price=180.0,
                savings_amount=220.0 - price, savings_percent=round((220.0 - price) / 220.0 * 100, 1),
                product_url=f"https://d.example/{shoe.id}", in_stock=True, is_active=True))


def _wl_many(db, n):
    retailer = _wl_retailer(db)
    shoes = [_wl_shoe(db, f"Model {i:03d}") for i in range(n)]
    for s in shoes:
        db.add(PriceRecord(shoe_id=s.id, retailer_id=retailer.id, product_url=f"p{s.id}",
                           price=200.0, in_stock=True, scraped_at=_datetime(2026, 6, 1)))
    db.commit()
    return shoes


def _embedded_watchlist_json(text):
    return json.loads(text.split("```json\n", 1)[1].rsplit("\n```", 1)[0])


import json  # noqa: E402  (used by the resource and session tests below)


def _decode_json_stream(text):
    """Decode back-to-back JSON values (one per MCP text block) into a list."""
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        obj, i = dec.raw_decode(text, i)
        out.append(obj)
    return out


def test_watchlist_default_entries_have_exactly_the_brief_keys(mcp_db):
    _wl_many(mcp_db, 2)
    out = mcp_server.get_watchlist()
    assert set(out) == {"entries", "total", "has_more"}
    assert out["entries"] and all(set(e) == WATCHLIST_BRIEF_KEYS for e in out["entries"])


def test_watchlist_best_deal_has_exactly_the_brief_deal_keys(mcp_db):
    retailer = _wl_retailer(mcp_db, "Altitude")
    shoe = _wl_shoe(mcp_db, "Pegasus")
    _wl_on_sale(mcp_db, shoe, retailer, price=140.0)
    mcp_db.commit()
    entry = mcp_server.get_watchlist()["entries"][0]
    assert entry["on_sale"] is True
    assert set(entry["best_deal"]) == BEST_DEAL_KEYS
    assert entry["best_deal"]["current_price"] == 140.0
    assert entry["best_deal"]["retailer_name"] == "Altitude"


def test_watchlist_best_deal_is_null_for_a_shoe_with_no_deal(mcp_db):
    _wl_many(mcp_db, 1)
    entry = mcp_server.get_watchlist()["entries"][0]
    assert entry["best_deal"] is None and entry["on_sale"] is False


def test_watchlist_exactly_limit_entries_has_more_false(mcp_db):
    _wl_many(mcp_db, 5)
    out = mcp_server.get_watchlist(limit=5)
    assert len(out["entries"]) == 5 and out["total"] == 5 and out["has_more"] is False


def test_watchlist_limit_plus_one_entries_has_more_true(mcp_db):
    _wl_many(mcp_db, 6)
    out = mcp_server.get_watchlist(limit=5)
    assert len(out["entries"]) == 5 and out["total"] == 6 and out["has_more"] is True


def test_watchlist_second_page_returns_the_remainder(mcp_db):
    _wl_many(mcp_db, 6)
    first = mcp_server.get_watchlist(limit=5)
    second = mcp_server.get_watchlist(limit=5, offset=5)
    assert len(second["entries"]) == 1 and second["has_more"] is False
    assert second["entries"][0]["shoe_id"] not in {e["shoe_id"] for e in first["entries"]}


def test_watchlist_offset_past_the_end_is_empty_with_correct_total(mcp_db):
    _wl_many(mcp_db, 3)
    out = mcp_server.get_watchlist(limit=20, offset=10)
    assert out == {"entries": [], "total": 3, "has_more": False}


def test_watchlist_limit_500_clamps_to_200(mcp_db):
    _wl_many(mcp_db, 201)
    out = mcp_server.get_watchlist(limit=500)
    assert len(out["entries"]) == 200 and out["total"] == 201 and out["has_more"] is True


def test_watchlist_limit_0_clamps_to_1(mcp_db):
    _wl_many(mcp_db, 3)
    out = mcp_server.get_watchlist(limit=0)
    assert len(out["entries"]) == 1 and out["has_more"] is True


def test_watchlist_negative_offset_clamps_to_0(mcp_db):
    _wl_many(mcp_db, 3)
    assert mcp_server.get_watchlist(offset=-4) == mcp_server.get_watchlist(offset=0)


def test_watchlist_on_sale_sorts_first_in_the_brief(mcp_db):
    retailer = _wl_retailer(mcp_db, "Altitude")
    _wl_shoe(mcp_db, "Aaa Plain")  # alphabetically first, not on sale
    onsale = _wl_shoe(mcp_db, "Zzz Sale")  # alphabetically last, on sale
    _wl_on_sale(mcp_db, onsale, retailer)
    mcp_db.commit()
    entries = mcp_server.get_watchlist()["entries"]
    assert entries[0]["model"] == "Zzz Sale" and entries[0]["on_sale"] is True
    assert entries[1]["model"] == "Aaa Plain"


def test_watchlist_detail_true_is_a_plain_full_list_ignoring_paging(mcp_db):
    _wl_many(mcp_db, 3)
    out = mcp_server.get_watchlist(limit=1, offset=2, detail=True)
    assert isinstance(out, list) and len(out) == 3
    assert all("last_seen" in e and "image_url" in e and "best_ever_at" in e for e in out)
    assert all(e["last_seen"] for e in out)


def test_watchlist_brief_values_match_the_full_entry(mcp_db):
    retailer = _wl_retailer(mcp_db, "Altitude")
    shoe = _wl_shoe(mcp_db, "Pegasus")
    _wl_on_sale(mcp_db, shoe, retailer, price=140.0)
    mcp_db.commit()
    brief = mcp_server.get_watchlist()["entries"][0]
    full = mcp_server.get_watchlist(detail=True)[0]
    top = WATCHLIST_BRIEF_KEYS - {"best_deal"}
    assert {k: brief[k] for k in top} == {k: full[k] for k in top}
    assert brief["best_deal"] == {k: full["best_deal"][k] for k in BEST_DEAL_KEYS}


def test_watchlist_resource_json_has_brief_keys_and_every_shoe(mcp_db):
    _wl_many(mcp_db, 25)
    data = _embedded_watchlist_json(deals_watchlist_resource())
    assert len(data["entries"]) == 25  # resource is not paged
    assert all(set(e) == WATCHLIST_BRIEF_KEYS for e in data["entries"])


def test_watchlist_resource_markdown_still_lists_the_shoes(mcp_db):
    _wl_many(mcp_db, 2)
    text = deals_watchlist_resource()
    assert text.startswith("# Deals Watchlist (2 shoes tracked)")


def test_watchlist_mixed_return_type_works_over_a_real_mcp_session(mcp_db):
    # Through the in-process MCP session the assistant uses (FastMCP, same tool
    # registration, structured output). Proves the Union return annotation serializes both shapes.
    _wl_many(mcp_db, 3)
    text, ok = _asyncio.run(call_tool_once("get_watchlist", {}))
    assert ok is True, text
    brief = json.loads(text)
    assert brief["total"] == 3 and len(brief["entries"]) == 3 and brief["has_more"] is False
    assert all(set(e) == WATCHLIST_BRIEF_KEYS for e in brief["entries"])

    text, ok = _asyncio.run(call_tool_once("get_watchlist", {"detail": True}))
    assert ok is True, text
    # FastMCP sends a list return as one JSON block per item, joined by newlines.
    full = _decode_json_stream(text)
    assert len(full) == 3 and "last_seen" in full[0]


# --- 12. scrape_health brief + detail (R14 T5b) -------------------------------

from app.models.models import ScrapeRun  # noqa: E402
from app.services import scrape_history as scrape_history_svc  # noqa: E402

SCRAPE_TOP_KEYS = {"retailers", "retailers_needing_attention", "needs_onboarding"}
SCRAPE_ROW_KEYS = {"retailer_id", "name", "health", "scraping_enabled", "last_status", "last_run_at",
                   "products_found", "error", "products_trend", "watchdog_alert", "watchdog_reason"}


def _sh_retailer(db, name):
    r = Retailer(name=name, base_url=f"https://{name.lower()}.example", is_active=True, scraping_enabled=True)
    db.add(r)
    db.flush()
    return r


def _sh_run(db, retailer, *, minute, status="success", products_found=5, error=None):
    run = ScrapeRun(retailer_id=retailer.id, status=status, trigger="manual", products_found=products_found,
                    error=error, started_at=_datetime(2026, 6, 1, 12, minute),
                    finished_at=_datetime(2026, 6, 1, 12, minute, 30))
    db.add(run)
    db.commit()
    return run


def _sh_row(out, name):
    return next(r for r in out["retailers"] if r["name"] == name)


def test_scrape_health_default_has_three_top_keys_and_no_recent_runs(mcp_db):
    _sh_run(mcp_db, _sh_retailer(mcp_db, "Altitude"), minute=0)
    out = mcp_server.scrape_health()
    assert set(out) == SCRAPE_TOP_KEYS
    assert "recent_runs" not in out


def test_scrape_health_default_retailer_rows_have_exactly_the_brief_keys(mcp_db):
    _sh_run(mcp_db, _sh_retailer(mcp_db, "Altitude"), minute=0)
    out = mcp_server.scrape_health()
    assert out["retailers"] and all(set(r) == SCRAPE_ROW_KEYS for r in out["retailers"])


def test_scrape_health_never_scraped_retailer_has_null_latest_fields(mcp_db):
    _sh_retailer(mcp_db, "Newbie")
    row = _sh_row(mcp_server.scrape_health(), "Newbie")
    assert row["health"] == "unknown"
    assert row["last_status"] is None
    assert row["last_run_at"] is None
    assert row["products_found"] is None
    assert row["error"] is None
    assert row["products_trend"] == []


def test_scrape_health_products_trend_is_newest_first_and_matches_runs(mcp_db):
    r = _sh_retailer(mcp_db, "Altitude")
    _sh_run(mcp_db, r, minute=0, products_found=10)
    _sh_run(mcp_db, r, minute=1, products_found=20)
    latest = _sh_run(mcp_db, r, minute=2, products_found=30)
    row = _sh_row(mcp_server.scrape_health(), "Altitude")
    assert row["products_trend"] == [30, 20, 10]
    assert row["products_found"] == 30
    assert row["last_status"] == "success"
    assert row["last_run_at"] == latest.started_at.isoformat()
    assert row["health"] == "ok"


def test_scrape_health_watchdog_fields_pass_through_after_three_failures(mcp_db):
    r = _sh_retailer(mcp_db, "Broken")
    for minute in range(3):
        _sh_run(mcp_db, r, minute=minute, status="error", products_found=0, error="boom")
    out = mcp_server.scrape_health()
    row = _sh_row(out, "Broken")
    assert row["watchdog_alert"] is True
    assert isinstance(row["watchdog_reason"], str) and row["watchdog_reason"]
    assert row["last_status"] == "error" and row["error"] == "boom"
    assert "Broken" in [a["name"] for a in out["retailers_needing_attention"]]


def test_scrape_health_detail_equals_the_service_payload_regression_lock(mcp_db):
    r = _sh_retailer(mcp_db, "Altitude")
    _sh_run(mcp_db, r, minute=0, products_found=10)
    _sh_run(mcp_db, r, minute=1, status="error", products_found=0, error="boom")
    assert mcp_server.scrape_health(detail=True) == scrape_history_svc.scrape_health(mcp_db)


# --- 12. deal brief + get_deals detail + deal resources (R14 T5c) -------------

from app.mcp_server._shared import _deal_brief, _deal_to_dict
from app.mcp_server.deals import _BRAND_DEALS_RESOURCE_CAP, active_deals_resource, brand_deals_resource
from app.services import deals as deals_svc

DEAL_BRIEF_KEYS = {"id", "shoe_id", "shoe", "retailer", "price", "savings_percent", "size_fit", "url"}


def _dl_retailer(db, name="Altitude"):
    r = Retailer(name=name, base_url=f"https://{name.lower()}.example")
    db.add(r)
    db.flush()
    return r


def _dl_deal(db, retailer, model, *, brand="Nike", savings=30.0, sizes=None):
    shoe = Shoe(brand=brand, model=model, msrp=200.0, is_active=True)
    db.add(shoe)
    db.flush()
    price = round(200.0 * (1 - savings / 100), 2)
    deal = Deal(shoe_id=shoe.id, retailer_id=retailer.id, current_price=price, target_price=180.0,
                savings_amount=200.0 - price, savings_percent=savings,
                product_url=f"https://d.example/{model}", in_stock=True, is_active=True,
                sizes_available=sizes, colorway="Black / White")
    db.add(deal)
    db.commit()
    return deal


def _dl_list(db, **kw):
    """The rows get_deals(detail=True) is built from, with get_deals' default args."""
    args = {"min_savings_percent": None, "brand": None, "shoe_type": None, "size": None, "limit": 20}
    args.update(kw)
    return deals_svc.list_deals(db, **args)


def test_deal_brief_has_exactly_the_brief_keys_and_matches_full_record(mcp_db):
    deal = _dl_deal(mcp_db, _dl_retailer(mcp_db), "Pegasus 41", sizes=["9", "10"])
    full = _deal_to_dict(_dl_list(mcp_db)[0])
    brief = _deal_brief(_dl_list(mcp_db)[0])
    assert set(brief) == DEAL_BRIEF_KEYS
    assert brief["id"] == full["id"] == deal.id
    assert brief["shoe_id"] == full["shoe_id"]
    assert brief["shoe"] == f"{full['brand']} {full['model']}" == "Nike Pegasus 41"
    assert brief["retailer"] == full["retailer"]
    assert brief["price"] == full["current_price"]
    assert brief["savings_percent"] == full["savings_percent"]
    assert brief["size_fit"] == full["size_fit"]
    assert brief["url"] == full["product_url"]


def test_get_deals_default_rows_have_exactly_the_brief_keys(mcp_db):
    _dl_deal(mcp_db, _dl_retailer(mcp_db), "Pegasus 41")
    _dl_deal(mcp_db, _dl_retailer(mcp_db, "TLH"), "Vaporfly 3", savings=40.0)
    out = mcp_server.get_deals()
    assert len(out) == 2
    assert all(set(row) == DEAL_BRIEF_KEYS for row in out)


def test_get_deals_detail_true_equals_the_full_flat_projection_regression_lock(mcp_db):
    _dl_deal(mcp_db, _dl_retailer(mcp_db), "Pegasus 41", savings=25.0, sizes=["9"])
    _dl_deal(mcp_db, _dl_retailer(mcp_db, "TLH"), "Vaporfly 3", savings=40.0)
    out = mcp_server.get_deals(detail=True)
    assert out == [_deal_to_dict(d) for d in _dl_list(mcp_db)]
    assert all("msrp" in row and "target_price" in row and "colorway" in row for row in out)


def test_get_deals_brand_filter_works_in_brief_mode(mcp_db):
    retailer = _dl_retailer(mcp_db)
    _dl_deal(mcp_db, retailer, "Pegasus 41", brand="Nike")
    _dl_deal(mcp_db, retailer, "Adios Pro 4", brand="Adidas")
    out = mcp_server.get_deals(brand="adidas")
    assert [row["shoe"] for row in out] == ["Adidas Adios Pro 4"]
    assert set(out[0]) == DEAL_BRIEF_KEYS


def test_get_deals_limit_caps_brief_rows_in_savings_order(mcp_db):
    retailer = _dl_retailer(mcp_db)
    for i, pct in enumerate([10.0, 30.0, 20.0]):
        _dl_deal(mcp_db, retailer, f"Model {i}", savings=pct)
    out = mcp_server.get_deals(limit=2)
    assert [row["savings_percent"] for row in out] == [30.0, 20.0]


def test_active_deals_resource_json_rows_have_exactly_the_brief_keys_and_total(mcp_db):
    retailer = _dl_retailer(mcp_db)
    _dl_deal(mcp_db, retailer, "Pegasus 41", savings=10.0)
    _dl_deal(mcp_db, retailer, "Vaporfly 3", savings=40.0)
    text = active_deals_resource()
    data = _embedded_json(text)
    assert data["total"] == 2
    assert len(data["deals"]) == 2
    assert all(set(row) == DEAL_BRIEF_KEYS for row in data["deals"])
    assert "# Active Deals (2 deals)" in text


def _brand_rows(text):
    return sum(1 for line in text.splitlines() if line.startswith("| ") and "% off |" in line)


def _dl_brand_batch(db, n, brand="Nike"):
    # Savings 1..n, so the highest-savings rows are the last ones inserted.
    retailer = _dl_retailer(db, "Bulk")
    for pct in range(1, n + 1):
        _dl_deal(db, retailer, f"Model {pct:03d}", brand=brand, savings=float(pct))


def test_brand_resource_at_cap_returns_all_rows_and_no_more_line(mcp_db):
    _dl_brand_batch(mcp_db, _BRAND_DEALS_RESOURCE_CAP)
    text = brand_deals_resource("Nike")
    data = _embedded_json(text)
    assert data["total"] == _BRAND_DEALS_RESOURCE_CAP
    assert len(data["deals"]) == _BRAND_DEALS_RESOURCE_CAP
    assert _brand_rows(text) == _BRAND_DEALS_RESOURCE_CAP
    assert f"# Active Deals — Nike ({_BRAND_DEALS_RESOURCE_CAP} deals)" in text
    assert "more deals" not in text


def test_brand_resource_over_cap_keeps_top_by_savings_and_shows_footer(mcp_db):
    _dl_brand_batch(mcp_db, _BRAND_DEALS_RESOURCE_CAP + 1)
    text = brand_deals_resource("Nike")
    data = _embedded_json(text)
    assert data["total"] == _BRAND_DEALS_RESOURCE_CAP + 1
    assert len(data["deals"]) == _BRAND_DEALS_RESOURCE_CAP
    assert _brand_rows(text) == _BRAND_DEALS_RESOURCE_CAP
    assert f"# Active Deals — Nike ({_BRAND_DEALS_RESOURCE_CAP + 1} deals)" in text
    assert "_1 more deals: use get_deals(brand=\"Nike\", limit=100)._" in text
    # The 1% deal is the one dropped; the kept rows run 51% down to 2%.
    savings = [row["savings_percent"] for row in data["deals"]]
    assert savings == sorted(savings, reverse=True)
    assert savings[0] == float(_BRAND_DEALS_RESOURCE_CAP + 1) and savings[-1] == 2.0
    assert set(data["deals"][0]) == DEAL_BRIEF_KEYS


def test_brand_resource_with_no_deals_returns_the_no_deals_message(mcp_db):
    _dl_brand_batch(mcp_db, 1, brand="Nike")
    assert brand_deals_resource("Asics") == "No active deals found for Asics"
