"""Tests for R2.7 T1 — the activity-tag vocabulary and its exposure through the
`unified_activities` seam (the columns T3's PB fix and T6's editor rely on)."""
from datetime import date

import pytest

from app.models.models import Activity
from app.services import activities as activities_svc
from app.utils.activity_tags import ACTIVITY_TAGS, is_valid_tag, suggest_tag_from_name


def _run(db, **kw):
    defaults = dict(source="manual", activity_type="Run", run_date=date(2026, 7, 1),
                    distance_km=10.0, avg_pace_s_per_km=300)
    defaults.update(kw)
    a = Activity(**defaults)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_vocabulary_is_the_expected_closed_set():
    # Schema-grade list — this test is the tripwire against casual growth.
    assert ACTIVITY_TAGS == (
        "Easy", "Long Run", "Recovery", "Tempo", "Intervals",
        "Track", "Workout", "Trail", "Parkrun", "Race",
    )
    assert is_valid_tag("Tempo")
    assert not is_valid_tag("tempo")   # canonical form only
    assert not is_valid_tag(None)
    assert not is_valid_tag("Fartlek")


def test_tag_and_elapsed_surface_through_the_seam(db):
    _run(db, activity_tag="Intervals", elapsed_time_s=2400, moving_time_s=1800)
    (ua,) = activities_svc.unified_activities(db)
    assert ua.activity_tag == "Intervals"
    assert ua.elapsed_time_s == 2400
    assert ua.activity_id is not None


def test_untagged_run_surfaces_none_tag(db):
    _run(db)
    (ua,) = activities_svc.unified_activities(db)
    assert ua.activity_tag is None


# --- R2.7 T8 — COROS-name tag inference (suggestion only) ------------------

@pytest.mark.parametrize("name,expected", [
    ("Morning Intervals", "Intervals"),
    ("6x800 repeats", "Intervals"),
    ("Track session", "Track"),
    ("Tempo 8k", "Tempo"),
    ("Threshold work", "Tempo"),
    ("Sunday Long Run", "Long Run"),
    ("long", "Long Run"),
    ("Mont-Royal trail", "Trail"),
    ("Ottawa Marathon", "Race"),
    ("Club Race", "Race"),
    ("Parkrun", "Parkrun"),
    ("Recovery shakeout", "Easy"),
    ("Easy 10k", "Easy"),
    ("morning jog", "Easy"),
])
def test_suggest_tag_maps_keywords(name, expected):
    assert suggest_tag_from_name(name) == expected


def test_suggest_tag_is_case_insensitive():
    assert suggest_tag_from_name("TEMPO RUN") == "Tempo"
    assert suggest_tag_from_name("pArKrUn") == "Parkrun"


def test_suggest_tag_precedence():
    # First matching rule wins (specificity ordering).
    assert suggest_tag_from_name("parkrun race") == "Parkrun"   # Parkrun before Race
    assert suggest_tag_from_name("easy long run") == "Long Run"  # Long Run before Easy


def test_suggest_tag_no_match_returns_none():
    assert suggest_tag_from_name("Afternoon Run") is None
    assert suggest_tag_from_name("") is None
    assert suggest_tag_from_name(None) is None


def test_suggested_tags_are_all_valid_vocabulary():
    for name in ("intervals", "long run", "tempo", "trail", "race", "parkrun", "easy", "track"):
        assert is_valid_tag(suggest_tag_from_name(name))
