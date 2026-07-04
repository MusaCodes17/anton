"""
Tests for the Strava import-health surface (GET /api/strava/status) used by
Settings → Sync & Scraping. Exercised at the handler level to match the
suite's service-oriented style (the TestClient/httpx combo isn't wired here).
"""
from datetime import date

from app.models.models import Activity
from app.routers.strava import get_strava_status


def test_status_empty(db):
    body = get_strava_status(db=db)
    assert body.activity_count == 0
    assert body.run_count == 0
    assert body.latest_activity_date is None
    assert body.imported_at is None


def test_status_counts_runs_and_latest_date(db):
    db.add_all([
        Activity(
            source="strava", strava_activity_id=1, activity_type="Run",
            run_date=date(2026, 6, 1), distance_km=10.0,
        ),
        Activity(
            source="strava", strava_activity_id=2, activity_type="Run",
            run_date=date(2026, 6, 25), distance_km=5.0,
        ),
        Activity(
            source="strava", strava_activity_id=3, activity_type="Ride",
            run_date=date(2026, 6, 10), distance_km=30.0,
        ),
    ])
    db.commit()

    body = get_strava_status(db=db)
    assert body.activity_count == 3
    assert body.run_count == 2
    assert body.latest_activity_date == date(2026, 6, 25)
