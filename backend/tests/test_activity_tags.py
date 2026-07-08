"""Tests for R2.7 T1 — the activity-tag vocabulary and its exposure through the
`unified_activities` seam (the columns T3's PB fix and T6's editor rely on)."""
from datetime import date

from app.models.models import Activity
from app.services import activities as activities_svc
from app.utils.activity_tags import ACTIVITY_TAGS, is_valid_tag


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
