"""Gear auto-matcher tests (§3)."""
from app.services.strava_gear import ShoeLike, auto_match, normalize_gear


def test_normalize_strips_brand_and_collapses_ws():
    assert normalize_gear("Adidas  Evo SL Teal") == "evo sl teal"
    assert normalize_gear("New Balance Fresh Foam X More") == "fresh foam x more"
    assert normalize_gear("Neo Zen ") == "neo zen"


def _shoes():
    return [
        ShoeLike(1, "Adidas", "Evo SL", "Evo SL Teal"),
        ShoeLike(2, "Adidas", "Evo SL", "Evo SL Purple"),
        ShoeLike(3, "Adidas", "Evo SL", "Evo SL Original"),
        ShoeLike(15, "Nike", "Streakfly", None),
        ShoeLike(11, "Mizuno", "Neo Zen", "Neo Zen Grey"),
        ShoeLike(12, "Mizuno", "Neo Zen", "Neo Zen Mint"),
    ]


def test_unique_nickname_match():
    r = auto_match(["Adidas Evo SL Teal"], _shoes())
    assert r.matched == {"Adidas Evo SL Teal": 1}


def test_unique_model_match():
    r = auto_match(["Nike Streakfly"], _shoes())
    assert r.matched == {"Nike Streakfly": 15}


def test_ambiguous_bare_model_left_unmatched():
    # "Adidas Evo SL" matches the shared model of shoes 1/2/3 → ambiguous.
    r = auto_match(["Adidas Evo SL"], _shoes())
    assert "Adidas Evo SL" not in r.matched
    assert set(r.ambiguous["Adidas Evo SL"]) == {1, 2, 3}


def test_unmatched_gear():
    r = auto_match(["PUMA DNE3"], _shoes())
    assert r.unmatched == ["PUMA DNE3"]


def test_mixed_batch_partitions_cleanly():
    gear = ["Adidas Evo SL Teal", "Mizuno Neo Zen", "PUMA DNE3", "Mizuno Neo Zen Mint"]
    r = auto_match(gear, _shoes())
    assert r.matched == {"Adidas Evo SL Teal": 1, "Mizuno Neo Zen Mint": 12}
    assert set(r.ambiguous["Mizuno Neo Zen"]) == {11, 12}
    assert r.unmatched == ["PUMA DNE3"]
