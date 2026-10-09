"""
Tests for planned races (P3.4): countdown math, target-pace derivation,
nullable handling, and past-race filtering. Exercised at the service level.
"""
from datetime import date, timedelta

from app.models.models import Activity, OwnedShoe, PlannedRace
from app.services import races as races_svc


def _race(db, name, race_date, distance_km=None, target_time_s=None, shoe_id=None, status="planned"):
    r = PlannedRace(
        name=name, race_date=race_date, distance_km=distance_km,
        target_time_s=target_time_s, planned_shoe_id=shoe_id, status=status,
    )
    db.add(r)
    db.flush()
    return r


def test_countdown_math(db):
    today = date(2026, 7, 4)
    future = _race(db, "Fall Marathon", today + timedelta(days=63))
    soon = _race(db, "This Week 10k", today + timedelta(days=6))
    todayr = _race(db, "Race Today", today)
    past = _race(db, "Old Race", today - timedelta(days=10))
    db.commit()

    races_svc.attach_derived(future, today)
    assert future.days_remaining == 63 and future.weeks_remaining == 9

    races_svc.attach_derived(soon, today)
    assert soon.days_remaining == 6 and soon.weeks_remaining == 0

    races_svc.attach_derived(todayr, today)
    assert todayr.days_remaining == 0 and todayr.weeks_remaining == 0  # race today = 0

    races_svc.attach_derived(past, today)
    assert past.days_remaining == -10  # negative → past


def test_target_pace_derivation_and_nullable(db):
    today = date(2026, 7, 4)
    # 10 km target 40:00 → 4:00/km
    with_target = _race(db, "Goal 10k", today + timedelta(days=30),
                        distance_km=10.0, target_time_s=2400)
    no_distance = _race(db, "Mystery", today + timedelta(days=30), target_time_s=2400)
    no_target = _race(db, "Just Show Up", today + timedelta(days=30), distance_km=21.1)
    db.commit()

    assert races_svc.attach_derived(with_target, today).target_pace == "4:00/km"
    assert races_svc.attach_derived(no_distance, today).target_pace is None
    assert races_svc.attach_derived(no_target, today).target_pace is None


def test_list_sorted_and_includes_past(db):
    today = date(2026, 7, 4)
    _race(db, "C", today + timedelta(days=30))
    _race(db, "A", today - timedelta(days=5), status="completed")
    _race(db, "B", today + timedelta(days=2))
    db.commit()

    races = races_svc.list_races(db, today=today)
    # soonest first, past races included (not filtered out server-side)
    assert [r.name for r in races] == ["A", "B", "C"]
    assert races[0].days_remaining == -5


def test_race_to_dict_shape_with_shoe(db):
    today = date(2026, 7, 4)
    shoe = OwnedShoe(brand="Nike", model="Alphafly", nickname="race day", current_mileage=0)
    db.add(shoe)
    db.flush()
    r = _race(db, "Berlin", today + timedelta(days=70), distance_km=42.195,
              target_time_s=3 * 3600, shoe_id=shoe.id)
    db.commit()

    d = races_svc.race_to_dict(r, today)
    assert d["weeks_remaining"] == 10
    assert d["target_pace"] is not None
    assert d["planned_shoe"]["nickname"] == "race day"


def test_activity_id_nullable_and_absent_by_default(db):
    # R2.7 T7 — a plain planned/manual race carries no linked activity.
    r = _race(db, "Unlinked", date(2026, 8, 1))
    db.commit()
    assert r.activity_id is None
    assert races_svc.race_to_dict(r)["activity_id"] is None


def test_promote_sets_activity_link(db):
    # R2.7 T7 — promoting an activity back-links the completed race to the run.
    a = Activity(source="strava", activity_type="Run", run_date=date(2026, 5, 4),
                 distance_km=10.0, moving_time_s=2400, name="10k", activity_tag="Race")
    db.add(a); db.commit(); db.refresh(a)

    race = races_svc.create_completed_from_activity(db, a.id)
    assert race.activity_id == a.id
    assert races_svc.race_to_dict(race)["activity_id"] == a.id


def test_activity_tagged_race_appears_in_list(db):
    # Activities tagged 'Race' with a past run_date are surfaced as synthetic
    # completed-race entries so the card shows them without a manual promote step.
    today = date(2026, 7, 9)
    a = Activity(source="coros", activity_type="Run", run_date=date(2026, 6, 1),
                 distance_km=10.0, moving_time_s=2400, name="Summer 10k", activity_tag="Race")
    db.add(a); db.commit(); db.refresh(a)

    races = races_svc.list_races(db, today=today)
    tagged = [r for r in races if getattr(r, "from_activity", False)]
    assert len(tagged) == 1
    assert tagged[0].name == "Summer 10k"
    assert tagged[0].activity_id == a.id
    assert tagged[0].status == "completed"
    assert tagged[0].id == -(a.id)


def test_already_linked_activity_not_duplicated(db):
    # An activity that is already back-linked from a PlannedRace row must NOT
    # also appear as a synthetic entry — it would show twice on the card.
    today = date(2026, 7, 9)
    a = Activity(source="strava", activity_type="Run", run_date=date(2026, 5, 4),
                 distance_km=10.0, moving_time_s=2400, name="10k", activity_tag="Race")
    db.add(a); db.commit(); db.refresh(a)
    races_svc.create_completed_from_activity(db, a.id)  # links PlannedRace → a.id

    races = races_svc.list_races(db, today=today)
    tagged = [r for r in races if getattr(r, "from_activity", False)]
    assert len(tagged) == 0   # already covered by the PlannedRace row


# ── Pruning planned races that were never run ─────────────────────────────

def _pending(db, run_date, status="pending"):
    from app.models.models import PendingCorosRun
    db.add(PendingCorosRun(
        label_id=f"L{run_date.isoformat()}{status}", sport_type=100, run_date=run_date,
        distance_km=5.0, moving_time_s=1500, avg_pace_s_per_km=300,
        start_timestamp=0, end_timestamp=1500, status=status,
    ))
    db.flush()


def test_prune_removes_unrun_past_planned_race(db):
    today = date(2026, 10, 8)
    _race(db, "Parkrun Time Trial", date(2026, 7, 18))
    db.commit()

    assert races_svc.prune_unrun_races(db, today) == ["Parkrun Time Trial"]
    assert db.query(PlannedRace).count() == 0
    assert all(r.name != "Parkrun Time Trial" for r in races_svc.list_races(db, today))


def test_prune_grace_boundary(db):
    today = date(2026, 10, 8)
    grace = races_svc.UNRUN_RACE_GRACE_DAYS
    _race(db, "Exactly at grace", today - timedelta(days=grace))       # pruned (inclusive)
    _race(db, "Inside grace", today - timedelta(days=grace - 1))       # kept — COROS may still sync
    _race(db, "Today", today)
    _race(db, "Future", today + timedelta(days=3))
    db.commit()

    assert races_svc.prune_unrun_races(db, today) == ["Exactly at grace"]
    assert {r.name for r in db.query(PlannedRace)} == {"Inside grace", "Today", "Future"}


def test_prune_keeps_race_with_a_run_that_day(db):
    today = date(2026, 10, 8)
    d = date(2026, 9, 20)
    _race(db, "Ran it", d)
    db.add(Activity(source="coros", activity_type="Run", run_date=d, distance_km=5.0, moving_time_s=1200))
    db.commit()

    assert races_svc.prune_unrun_races(db, today) == []


def test_prune_keeps_race_with_coros_run_waiting_to_sync(db):
    today = date(2026, 10, 8)
    d = date(2026, 9, 20)
    _race(db, "In the inbox", d)
    _pending(db, d)
    db.commit()

    assert races_svc.prune_unrun_races(db, today) == []


def test_prune_ignores_dismissed_inbox_runs(db):
    today = date(2026, 10, 8)
    d = date(2026, 9, 20)
    _race(db, "Dismissed run only", d)
    _pending(db, d, status="dismissed")
    db.commit()

    assert races_svc.prune_unrun_races(db, today) == ["Dismissed run only"]


def test_prune_never_touches_completed_skipped_or_linked(db):
    today = date(2026, 10, 8)
    d = date(2026, 7, 18)
    _race(db, "Done", d, status="completed")
    _race(db, "Skipped on purpose", d, status="skipped")
    a = Activity(source="strava", activity_type="Run", run_date=date(2026, 7, 1), distance_km=5.0, moving_time_s=1200)
    db.add(a)
    db.flush()
    linked = _race(db, "Linked", d)
    linked.activity_id = a.id
    db.commit()

    assert races_svc.prune_unrun_races(db, today) == []
    assert db.query(PlannedRace).count() == 3
