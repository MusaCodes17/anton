"""R5.5 — shoe performance and wear curves.

Rules under test: the steady filter is the form trend's (tagged / short / no-HR
runs count in `runs` but not `steady_runs`), exactly 10 steady runs is enough
and 9 refuses a verdict, models merge case-insensitively, the wear curve keeps
empty weeks and starts from starting_mileage, type suggestions need 3 retired
pairs and round to 10 km, and REST == MCP.
"""
from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app import mcp_server
from app.models.models import OwnedShoe
from app.routers.insights import get_rotation_insights, get_shoe_insights
from app.services import insights, rotation

START = date(2026, 3, 2)   # a Monday


def shoe(db, brand="Nike", model="Pegasus 41", **kw):
    s = OwnedShoe(brand=brand, model=model, **kw)
    db.add(s)
    db.commit()
    return s


def steady(db, s, n, start=START, km=10.0, hr=150, tag=None):
    for i in range(n):
        rotation.log_run(db, s.id, distance_km=km, run_date=start + timedelta(days=i),
                         avg_hr=hr, moving_time_s=int(km * 330), activity_tag=tag)


def test_non_steady_runs_count_in_runs_but_not_steady(db):
    s = shoe(db)
    steady(db, s, 1)
    steady(db, s, 1, start=START + timedelta(days=20), tag="Tempo")
    rotation.log_run(db, s.id, distance_km=3.0, run_date=START + timedelta(days=30), avg_hr=150, moving_time_s=990)
    rotation.log_run(db, s.id, distance_km=10.0, run_date=START + timedelta(days=31), moving_time_s=3300)
    p = insights.shoe_performance(db, s.id)
    assert (p.runs, p.steady_runs) == (4, 1)
    assert p.km == 33.0


def test_nine_steady_runs_refuse_a_verdict_ten_give_one(db):
    s = shoe(db)
    steady(db, s, 9)
    p = insights.shoe_performance(db, s.id)
    assert not p.enough_data and p.median_m_per_beat is None
    assert p.median_pace_s_per_km is None and p.median_avg_hr is None
    steady(db, s, 1, start=START + timedelta(days=40))
    p = insights.shoe_performance(db, s.id)
    assert p.enough_data and p.steady_runs == 10
    assert p.median_pace_s_per_km == 330 and p.median_avg_hr == 150
    assert p.median_m_per_beat == round(10000 / (150 * 3300 / 60), 3)
    assert p.heuristic is True and "used for" in p.caveat


def test_models_merge_case_insensitively_across_pairs(db):
    a = shoe(db, brand="Nike", model="Pegasus 41")
    b = shoe(db, brand=" nike", model="pegasus 41 ")
    c = shoe(db, brand="Hoka", model="Clifton 9")
    steady(db, a, 6)
    steady(db, b, 5, start=START + timedelta(days=30))
    steady(db, c, 2, start=START + timedelta(days=60))
    models = insights.model_performance(db)
    assert [m.model for m in models] == ["Pegasus 41", "Clifton 9"]     # sorted by runs desc
    peg = models[0]
    assert peg.pair_ids == [a.id, b.id] and peg.runs == 11 and peg.enough_data


def test_wear_curve_has_empty_middle_week_and_starts_at_starting_mileage(db):
    s = shoe(db, starting_mileage=100.0, current_mileage=100.0)
    rotation.log_run(db, s.id, distance_km=10, run_date=START)                       # 2026-W10
    rotation.log_run(db, s.id, distance_km=20, run_date=START + timedelta(days=14))  # 2026-W12
    db.refresh(s)
    w = insights.wear_curve(db, s.id)
    assert [(x.week, x.km, x.cumulative_km) for x in w.weeks] == [
        ("2026-W10", 10.0, 110.0), ("2026-W11", 0.0, 110.0), ("2026-W12", 20.0, 130.0)]
    assert w.current_mileage == 130.0 and w.mileage_limit is None and w.pct_of_limit is None


def test_wear_curve_pct_of_limit(db):
    s = shoe(db, current_mileage=300.0, mileage_limit=800.0)
    w = insights.wear_curve(db, s.id)
    assert w.weeks == [] and w.pct_of_limit == 37.5


def retired(db, n, finals, shoe_type="daily_trainer"):
    for f in finals[:n]:
        shoe(db, shoe_type=shoe_type, status="retired", current_mileage=f)


def test_wear_by_type_needs_three_retired_for_a_suggestion(db):
    retired(db, 2, [640.0, 700.0])
    shoe(db, shoe_type="daily_trainer", status="active", current_mileage=50.0)   # ignored
    t = insights.wear_by_type(db)[0]
    assert (t.retired_count, t.median_final_km, t.suggested_limit_km) == (2, 670.0, None)
    shoe(db, shoe_type="daily_trainer", status="retired", current_mileage=655.0)
    t = insights.wear_by_type(db)[0]
    assert t.retired_count == 3 and t.median_final_km == 655.0 and t.suggested_limit_km == 660.0


def test_wear_by_type_ignores_untyped_and_active(db):
    shoe(db, status="retired", current_mileage=500.0)
    shoe(db, shoe_type="tempo", status="active", current_mileage=500.0)
    assert insights.wear_by_type(db) == []


def test_missing_shoe_raises_lookup_and_rest_404(db):
    with pytest.raises(LookupError):
        insights.shoe_performance(db, 999)
    with pytest.raises(HTTPException) as e:
        get_shoe_insights(999, db=db)
    assert e.value.status_code == 404


def test_endpoints_and_mcp_tools_agree(db, monkeypatch):
    s = shoe(db, shoe_type="tempo")
    steady(db, s, 10)
    retired(db, 3, [400.0, 420.0, 410.0], shoe_type="tempo")

    @contextmanager
    def fake_session():
        yield db
    monkeypatch.setattr(mcp_server._core, "get_session", fake_session)

    assert get_shoe_insights(s.id, db=db).model_dump() == mcp_server.get_shoe_insights(s.id)
    rest = get_rotation_insights(db=db).model_dump()
    assert rest == mcp_server.get_rotation_insights()
    assert rest["wear_by_type"][0]["suggested_limit_km"] == 410.0
    assert "error" in mcp_server.get_shoe_insights(999)
