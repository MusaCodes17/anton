"""COROS direct sync §5 — deterministic shoe suggestion.

Pins the rule ported from the `sync_coros_runs` prompt: pace primary, distance
secondary, active shoes only, lowest mileage wins, explicit "no match" instead of
a forced pick. Boundaries are named because the bands are inclusive and overlap.
"""
from app.models.models import OwnedShoe
from app.services.coros_suggestion import distance_types, pace_types, suggest_shoe


def P(m, s=0):
    return m * 60 + s


def shoe(db, type_, mileage, *, status="active", model=None):
    s = OwnedShoe(brand="B", model=model or f"{type_}-{mileage}", shoe_type=type_,
                  starting_mileage=0, current_mileage=mileage, status=status)
    db.add(s)
    db.commit()
    return s


# --- the signals ------------------------------------------------------------------

def test_pace_bands_match_the_prompt():
    assert pace_types(P(3, 20)) == {"short_distance_racer", "intervals"}
    assert pace_types(P(4, 12)) == {"tempo", "long_distance_racer", "long_run"}   # 3:30–4:15 ∪ 4:00–4:30
    assert pace_types(P(5, 0)) == {"daily_trainer"}
    assert pace_types(P(6, 0)) == {"recovery", "daily_trainer"}


def test_pace_boundaries():
    assert "intervals" in pace_types(P(3, 29)) and "intervals" not in pace_types(P(3, 30))
    assert "tempo" in pace_types(P(3, 30)) and "tempo" in pace_types(P(4, 15)) and "tempo" not in pace_types(P(4, 16))
    assert pace_types(P(4, 30)) == {"long_run", "daily_trainer"}        # 4:30 closes one band, opens the next
    assert pace_types(P(5, 30)) == {"daily_trainer"}                    # "4:30–5:30" is inclusive
    assert "recovery" not in pace_types(P(5, 30)) and "recovery" in pace_types(P(5, 31))


def test_distance_bands_and_boundaries():
    assert distance_types(3.0) == {"intervals", "short_distance_racer"}
    assert distance_types(4.99) == {"intervals", "short_distance_racer"}
    assert distance_types(5.0) == {"daily_trainer"}                     # 5 km is NOT "<5"
    assert distance_types(10.0) == {"daily_trainer"}
    assert distance_types(16.0) == {"daily_trainer", "tempo"}           # 5–16 and 16–22 both include 16
    assert distance_types(21.0) == {"tempo", "daily_trainer"}           # ">21" excludes 21 exactly
    assert distance_types(21.1) == {"tempo", "daily_trainer", "long_run", "long_distance_racer"}
    assert distance_types(30.0) == {"long_run", "long_distance_racer"}


# --- resolution -------------------------------------------------------------------

def test_agreeing_signals_pick_lowest_mileage_of_that_type(db):
    shoe(db, "daily_trainer", 400)
    low = shoe(db, "daily_trainer", 120)
    shoe(db, "tempo", 10)                       # lower mileage but wrong type
    s = suggest_shoe(db, distance_km=10.0, avg_pace_s_per_km=P(5, 0))
    assert s.shoe_id == low.id and "agree" in s.reason and "daily_trainer" in s.reason


def test_short_fast_run_goes_to_intervals_or_racer(db):
    a = shoe(db, "intervals", 80)
    shoe(db, "short_distance_racer", 150)
    assert suggest_shoe(db, distance_km=3.0, avg_pace_s_per_km=P(3, 20)).shoe_id == a.id


def test_long_run_at_marathon_ish_pace(db):
    lr = shoe(db, "long_run", 300)
    shoe(db, "daily_trainer", 50)
    s = suggest_shoe(db, distance_km=25.0, avg_pace_s_per_km=P(4, 15))     # pace {tempo,LDR,long_run} ∩ dist {long_run,LDR}
    assert s.shoe_id == lr.id


def test_conflict_falls_back_to_union_lowest_mileage(db):
    # 4:12/km (tempo/LDR/long_run) over 12 km (daily_trainer): no overlap -> union
    shoe(db, "tempo", 300)
    d = shoe(db, "daily_trainer", 90)
    s = suggest_shoe(db, distance_km=12.0, avg_pace_s_per_km=P(4, 12))
    assert s.shoe_id == d.id and "pace suggests" in s.reason and "distance suggests" in s.reason


def test_agreed_type_absent_from_rotation_falls_back(db):
    r = shoe(db, "recovery", 200)               # pace 6:00 -> {recovery, daily}; 10 km -> {daily}; no daily shoe
    s = suggest_shoe(db, distance_km=10.0, avg_pace_s_per_km=P(6, 0))
    assert s.shoe_id == r.id and "no active shoe of the agreed type" in s.reason


def test_equal_mileage_ties_break_on_lowest_id(db):
    a = shoe(db, "daily_trainer", 100)
    shoe(db, "daily_trainer", 100)
    assert suggest_shoe(db, distance_km=10.0, avg_pace_s_per_km=P(5, 0)).shoe_id == a.id


# --- never suggest the wrong shoe ----------------------------------------------------

def test_retired_and_for_sale_shoes_are_never_suggested(db):
    shoe(db, "daily_trainer", 5, status="retired")
    shoe(db, "daily_trainer", 6, status="for_sale")
    active = shoe(db, "daily_trainer", 500)
    assert suggest_shoe(db, distance_km=10.0, avg_pace_s_per_km=P(5, 0)).shoe_id == active.id


def test_only_retired_match_means_no_suggestion(db):
    shoe(db, "daily_trainer", 5, status="retired")
    s = suggest_shoe(db, distance_km=10.0, avg_pace_s_per_km=P(5, 0))
    assert s.shoe_id is None and "No active shoe" in s.reason


def test_no_matching_type_says_so_explicitly(db):
    shoe(db, "trail", 10)
    s = suggest_shoe(db, distance_km=10.0, avg_pace_s_per_km=P(5, 0))
    assert s.shoe_id is None and "fits" in s.reason and "daily_trainer" in s.reason


def test_empty_rotation_and_untyped_shoes(db):
    assert suggest_shoe(db, distance_km=10.0, avg_pace_s_per_km=P(5, 0)).shoe_id is None
    shoe(db, None, 1)
    assert suggest_shoe(db, distance_km=10.0, avg_pace_s_per_km=P(5, 0)).shoe_id is None


def test_reason_fits_the_column(db):
    shoe(db, "tempo", 1)
    s = suggest_shoe(db, distance_km=12.0, avg_pace_s_per_km=P(4, 12))
    assert len(s.reason) <= 200
