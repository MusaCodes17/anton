"""
Tests for the unified activity feed (§3 Phase-3a) over the canonical
`activities` table (§3 Phase-5). Exercised at the service/handler level to
match the suite's style.

In v2 every run is a single `Activity` row; a `ShoeRun` is just an attribution
row pointing an activity at an owned shoe. There is no more "linked/unlinked"
dedup — a physical run exists once by construction.
"""
from datetime import date

from app.models.models import Activity, OwnedShoe, ShoeRun
from app.routers.activities import get_activities
from app.services import activities as activities_svc
from app.services import strava_stats


def _activity(db, *, source="strava", run_date, dist, pace_s=300, hr=150,
              atype="Run", moving_s=None, name="Run", said=None, coros_id=None):
    """A canonical activity. Strava rows carry a real moving_time_s; COROS/manual
    rows leave it None (pace reconstructs it), mirroring production."""
    a = Activity(
        source=source,
        activity_type=atype,
        name=name,
        run_date=run_date,
        distance_km=dist,
        moving_time_s=(moving_s if moving_s is not None else (int(pace_s * dist) if source == "strava" else None)),
        avg_hr=hr,
        avg_pace_s_per_km=pace_s,
        elevation_gain_m=10.0,
        strava_activity_id=said,
        coros_activity_id=coros_id,
    )
    db.add(a)
    db.flush()
    return a


def _owned(db, brand="Nike", model="Vaporfly"):
    s = OwnedShoe(brand=brand, model=model, nickname="racer", current_mileage=0)
    db.add(s)
    db.flush()
    return s


def _attribute(db, activity, shoe):
    r = ShoeRun(activity_id=activity.id, owned_shoe_id=shoe.id)
    db.add(r)
    db.flush()
    return r


def test_non_runs_excluded_and_sorted_desc(db):
    _activity(db, said=1, run_date=date(2026, 6, 1), dist=10.0)
    _activity(db, said=2, run_date=date(2026, 6, 20), dist=5.0)
    _activity(db, said=3, run_date=date(2026, 6, 10), dist=30.0, atype="Ride")  # excluded
    db.commit()

    items = activities_svc.unified_activities(db)
    assert [a.strava_activity_id for a in items] == [2, 1]  # newest first, ride dropped
    assert all(a.source == "strava" for a in items)


def test_run_appears_once_with_shoe_attribution(db):
    shoe = _owned(db)
    a = _activity(db, said=100, run_date=date(2026, 6, 15), dist=10.0)
    _attribute(db, a, shoe)
    db.commit()

    items = activities_svc.unified_activities(db)
    assert len(items) == 1
    got = items[0]
    assert got.strava_activity_id == 100
    assert got.source == "strava"
    assert got.shoe is not None and got.shoe.model == "Vaporfly"
    assert got.shoe_run_id is not None


def test_post_export_run_appears(db):
    shoe = _owned(db)
    _activity(db, said=1, run_date=date(2026, 6, 1), dist=8.0)
    # a COROS run recorded AFTER the frozen export — its own activity + attribution
    coros = _activity(db, source="coros", run_date=date(2026, 7, 2), dist=12.0, coros_id="c1")
    _attribute(db, coros, shoe)
    db.commit()

    items = activities_svc.unified_activities(db)
    assert len(items) == 2
    newest = items[0]
    assert newest.date == date(2026, 7, 2)
    assert newest.source == "coros"
    assert newest.shoe.id == shoe.id


def test_filters_year_month_shoe_min_distance_and_pagination(db):
    shoe = _owned(db)
    _activity(db, said=1, run_date=date(2025, 12, 1), dist=5.0)
    _activity(db, said=2, run_date=date(2026, 6, 5), dist=3.0)
    _activity(db, said=3, run_date=date(2026, 6, 25), dist=20.0)
    manual = _activity(db, source="manual", run_date=date(2026, 6, 15), dist=15.0)
    _attribute(db, manual, shoe)
    db.commit()

    y2026 = activities_svc.unified_activities(db, year=2026)
    assert len(y2026) == 3  # strava 2 & 3 + the manual run; strava 1 is 2025
    assert {2, 3} <= {a.strava_activity_id for a in y2026 if a.strava_activity_id}
    assert len(activities_svc.unified_activities(db, month=6)) == 3
    assert all(a.shoe and a.shoe.id == shoe.id
               for a in activities_svc.unified_activities(db, shoe_id=shoe.id))
    assert all(a.distance_km >= 10 for a in activities_svc.unified_activities(db, min_distance_km=10))
    # pagination
    page1 = activities_svc.unified_activities(db, limit=2, offset=0)
    page2 = activities_svc.unified_activities(db, limit=2, offset=2)
    assert len(page1) == 2 and len(page2) == 2
    assert not ({id(x) for x in page1} & {id(x) for x in page2})


def test_filter_composes_with_pagination_newest_first(db):
    # R2.3: filters + ORDER BY + LIMIT/OFFSET all run in one SQL query. A
    # date_from filter composed with paging must page a *filtered, sorted*
    # result — newest first, no page overlap, the pre-window run never appears.
    _activity(db, said=1, run_date=date(2026, 1, 1), dist=5.0)   # before window
    for i, d in enumerate([date(2026, 6, 1), date(2026, 6, 2),
                           date(2026, 6, 3), date(2026, 6, 4)], start=10):
        _activity(db, said=i, run_date=d, dist=5.0)
    db.commit()

    page1 = activities_svc.unified_activities(
        db, date_from=date(2026, 5, 1), limit=2, offset=0)
    page2 = activities_svc.unified_activities(
        db, date_from=date(2026, 5, 1), limit=2, offset=2)
    assert [a.date for a in page1] == [date(2026, 6, 4), date(2026, 6, 3)]
    assert [a.date for a in page2] == [date(2026, 6, 2), date(2026, 6, 1)]
    # the January run is filtered out entirely, not merely off the last page
    assert all(a.date.year == 2026 and a.date.month == 6
               for a in page1 + page2)


def test_summary_includes_all_sources(db):
    shoe = _owned(db)
    _activity(db, said=1, run_date=date(2026, 6, 1), dist=10.0)
    coros = _activity(db, source="coros", run_date=date(2026, 6, 20), dist=5.0, coros_id="c1")
    _attribute(db, coros, shoe)
    db.commit()

    monthly = strava_stats.training_summary(db, "monthly")
    jun = next(b for b in monthly if b.period == "2026-06")
    assert jun.run_count == 2
    assert jun.total_km == 15.0


def test_date_range_filters_activities_and_summary(db):
    # Three runs across three months; a from..to window keeps only the middle.
    _activity(db, said=30, run_date=date(2026, 4, 10), dist=6.0)
    _activity(db, said=31, run_date=date(2026, 5, 15), dist=7.0)
    _activity(db, said=32, run_date=date(2026, 6, 20), dist=8.0)
    db.commit()

    # Inclusive window May 1 – May 31 → only the May run.
    ranged = activities_svc.unified_activities(
        db, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31))
    assert [a.distance_km for a in ranged] == [7.0]

    # date_from only (open-ended upper bound) keeps May + June.
    since_may = activities_svc.unified_activities(db, date_from=date(2026, 5, 1))
    assert sorted(a.distance_km for a in since_may) == [7.0, 8.0]

    # The summary honours the same window.
    summary = strava_stats.training_summary(
        db, period="monthly", date_from=date(2026, 5, 1), date_to=date(2026, 5, 31))
    assert len(summary) == 1
    assert summary[0].period == "2026-05"
    assert summary[0].total_km == 7.0


def test_records_attribute_shoe(db):
    shoe = _owned(db)
    # A fast 10k attributed to a shoe, and a slower unattributed 10k.
    fast = _activity(db, said=1, run_date=date(2026, 6, 1), dist=10.0, pace_s=240)
    _attribute(db, fast, shoe)
    _activity(db, said=2, run_date=date(2026, 5, 1), dist=10.0, pace_s=300)
    db.commit()

    # smoke: router adapter returns without error (explicit args since we bypass
    # FastAPI's Query default resolution by calling it directly)
    resp = get_activities(year=None, month=None, shoe_id=None,
                          min_distance_km=None, limit=20, offset=0, db=db)
    assert len(resp) >= 2

    result = strava_stats.personal_bests(db)
    ten = _band(result.best_efforts, "10k")
    assert ten.avg_pace == "4:00/km"          # the faster one won
    assert ten.total_time_s == 2400           # no elapsed time here → moving clock
    assert ten.clock == "moving"
    assert ten.shoe is not None and ten.shoe["id"] == shoe.id
    assert result.excluded_count == 0
    assert result.race_pbs == []              # nothing tagged or linked as a race


# ── Records: two lists on the elapsed clock (R8.1) ───────────────────────────

def _band(records, band):
    return next((b for b in records if b.band == band), None)


def _timed(db, *, said, dist, moving_s, elapsed_s, tag=None, run_date=date(2026, 6, 1)):
    a = _activity(db, said=said, run_date=run_date, dist=dist,
                  pace_s=round(moving_s / dist), moving_s=moving_s)
    a.elapsed_time_s = elapsed_s
    a.activity_tag = tag
    db.flush()
    return a


def test_records_are_timed_on_elapsed_time(db):
    # A stop-heavy run with the faster moving time loses to a clean run once
    # its standing rests count — this is what retired the 1.5x ratio guard.
    _timed(db, said=1, dist=5.0, moving_s=1000, elapsed_s=1400)   # untagged, stops a lot
    clean = _timed(db, said=2, dist=5.0, moving_s=1050, elapsed_s=1060)
    db.commit()
    five = _band(strava_stats.personal_bests(db).best_efforts, "5k")
    assert five.activity_id == clean.id
    assert five.total_time_s == 1060 and five.clock == "elapsed"
    assert five.avg_pace == "3:32/km"          # 1060 s / 5 km — pace from the same clock


def test_retagging_a_race_removes_it_from_race_pbs(db):
    race = _timed(db, said=3, dist=10.0, moving_s=2100, elapsed_s=2110, tag="Race")
    db.commit()
    result = strava_stats.personal_bests(db)
    assert _band(result.race_pbs, "10k").activity_id == race.id
    assert _band(result.best_efforts, "10k").activity_id == race.id   # races count there too

    race.activity_tag = "Tempo"                # the reported bug
    db.commit()
    result = strava_stats.personal_bests(db)
    assert result.race_pbs == []
    assert _band(result.best_efforts, "10k").activity_id == race.id   # still a fast run


def test_parkrun_counts_as_a_race_pb(db):
    _timed(db, said=4, dist=5.0, moving_s=1000, elapsed_s=1005, tag="Parkrun")
    db.commit()
    assert _band(strava_stats.personal_bests(db).race_pbs, "5k").total_time_s == 1005


def test_untagged_run_linked_to_a_race_is_a_race_pb(db):
    from app.models.models import PlannedRace
    a = _timed(db, said=5, dist=21.1, moving_s=4600, elapsed_s=4631)
    db.add(PlannedRace(name="Spring Half", race_date=date(2026, 6, 1), status="completed", activity_id=a.id))
    db.commit()
    assert _band(strava_stats.personal_bests(db).race_pbs, "half").activity_id == a.id


def test_intervals_and_track_never_set_a_best_effort(db):
    _timed(db, said=6, dist=5.0, moving_s=1100, elapsed_s=1110)
    _timed(db, said=7, dist=5.0, moving_s=800, elapsed_s=900, tag="Intervals")
    _timed(db, said=8, dist=5.0, moving_s=800, elapsed_s=900, tag="Track")
    db.commit()
    result = strava_stats.personal_bests(db)
    assert _band(result.best_efforts, "5k").total_time_s == 1110
    assert result.excluded_count == 2
    assert result.excluded_reason == "2 interval/track session"


def test_record_carries_canonical_activity_id(db):
    # The card deep-links to the /activities/:id editor (to retag a run).
    a = _activity(db, said=9, run_date=date(2026, 6, 6), dist=10.0, pace_s=240)
    db.commit()
    assert _band(strava_stats.personal_bests(db).best_efforts, "10k").activity_id == a.id


def test_promoted_race_result_uses_elapsed_time(db):
    from app.services import races as races_svc
    a = _timed(db, said=10, dist=10.0, moving_s=2100, elapsed_s=2130, tag="Race")
    db.commit()
    assert races_svc.create_completed_from_activity(db, a.id).result_time_s == 2130
