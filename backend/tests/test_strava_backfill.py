"""
Dedup + backfill tests (§4/§5): exact/tolerance matching, multi-candidate
ambiguity, date-shift widening, shoe-conflict logging, backfill idempotency,
and the mileage-preservation property.
"""
from datetime import date, timedelta

from app.models.models import OwnedShoe, ShoeRun, StravaActivity, StravaGearMapping
from app.services import strava_backfill as bf


def _shoe(db, sid, brand="Adidas", model="Evo SL", nickname=None, starting=0.0):
    s = OwnedShoe(
        id=sid, brand=brand, model=model, nickname=nickname,
        starting_mileage=starting, current_mileage=starting, status="active",
    )
    db.add(s)
    return s


def _run(db, shoe_id, d, dist, source="manual"):
    r = ShoeRun(owned_shoe_id=shoe_id, distance_km=dist, run_date=d, source=source)
    db.add(r)
    return r


def _strava(db, sid, d, dist, gear=None, pace_s=300, hr=150):
    a = StravaActivity(
        strava_activity_id=sid, activity_type="Run", run_date=d,
        distance_km=dist, avg_pace_s_per_km=pace_s, avg_hr=hr, gear_name=gear,
    )
    db.add(a)
    return a


def _map(db, gear, shoe_id):
    db.add(StravaGearMapping(gear_name=gear, owned_shoe_id=shoe_id))


D = date(2026, 6, 1)


def test_exact_match_links_not_creates(db):
    _shoe(db, 1)
    _run(db, 1, D, 10.0)
    _strava(db, 5001, D, 10.0, gear="Adidas Evo SL")
    _map(db, "Adidas Evo SL", 1)
    db.commit()

    rep = bf.plan_backfill(db)
    assert len(rep.matched) == 1
    assert not rep.to_create
    assert rep.matched[0].strava_activity_id == 5001


def test_distance_tolerance_match(db):
    _shoe(db, 1)
    _run(db, 1, D, 10.0)
    _strava(db, 5001, D, 10.08, gear="Adidas Evo SL")  # within 0.1km
    _map(db, "Adidas Evo SL", 1)
    db.commit()

    rep = bf.plan_backfill(db)
    assert len(rep.matched) == 1 and not rep.to_create


def test_multi_candidate_tie_is_ambiguous(db):
    _shoe(db, 1)
    _run(db, 1, D, 10.0)
    _run(db, 1, D, 10.0)  # two identical-distance runs same day → tie
    _strava(db, 5001, D, 10.0, gear="Adidas Evo SL")
    _map(db, "Adidas Evo SL", 1)
    db.commit()

    rep = bf.plan_backfill(db)
    assert not rep.matched
    assert len(rep.ambiguous) == 1
    assert not rep.to_create  # ambiguous is never backfilled either


def test_multi_candidate_closest_distance_wins(db):
    _shoe(db, 1)
    _run(db, 1, D, 10.0)   # closer
    _run(db, 1, D, 10.09)  # farther but still in tolerance
    _strava(db, 5001, D, 10.0, gear="Adidas Evo SL")
    _map(db, "Adidas Evo SL", 1)
    db.commit()

    rep = bf.plan_backfill(db)
    assert len(rep.matched) == 1 and not rep.ambiguous


def test_date_shift_widening_flags_not_links(db):
    _shoe(db, 1)
    _run(db, 1, D + timedelta(days=1), 10.0)  # one day off
    _strava(db, 5001, D, 10.0, gear="Adidas Evo SL")
    _map(db, "Adidas Evo SL", 1)
    db.commit()

    rep = bf.plan_backfill(db)
    assert not rep.matched
    assert len(rep.date_shift) == 1
    assert not rep.to_create  # date-shift is manual-only, never auto-created


def test_shoe_conflict_is_logged(db):
    _shoe(db, 1, nickname="A")
    _shoe(db, 2, nickname="B")
    _run(db, 2, D, 10.0)               # logged to shoe 2
    _strava(db, 5001, D, 10.0, gear="Adidas Evo SL")
    _map(db, "Adidas Evo SL", 1)       # but gear maps to shoe 1
    db.commit()

    rep = bf.plan_backfill(db)
    assert len(rep.matched) == 1
    assert rep.matched[0].conflict is True
    assert len(rep.conflicts) == 1
    assert rep.matched[0].run_shoe_id == 2  # existing assignment kept


def test_backfill_creates_for_unmatched_mapped_gear(db):
    _shoe(db, 1, starting=0.0)
    _strava(db, 5001, D, 10.0, gear="Adidas Evo SL")
    _map(db, "Adidas Evo SL", 1)
    db.commit()

    rep = bf.plan_backfill(db)
    assert len(rep.to_create) == 1
    assert rep.to_create[0].owned_shoe_id == 1
    assert rep.to_create[0].avg_pace == "5:00/km"


def test_unmapped_and_no_gear_are_skipped(db):
    _shoe(db, 1)
    _strava(db, 5001, D, 10.0, gear="Unknown Shoe")  # gear present, unmapped
    _strava(db, 5002, D, 8.0, gear=None)             # no gear
    db.commit()

    rep = bf.plan_backfill(db)
    assert rep.skipped_unmapped == [5001]
    assert rep.skipped_no_gear == [5002]
    assert not rep.to_create


def test_execute_is_idempotent(db):
    _shoe(db, 1, starting=100.0)
    _strava(db, 5001, D, 10.0, gear="Adidas Evo SL")
    _map(db, "Adidas Evo SL", 1)
    db.commit()

    r1 = bf.execute_backfill(db)
    assert len(r1.to_create) == 1
    mileage_after = db.get(OwnedShoe, 1).current_mileage
    runs_after = db.query(ShoeRun).count()

    r2 = bf.execute_backfill(db)  # second pass
    assert not r2.to_create
    assert db.query(ShoeRun).count() == runs_after
    assert db.get(OwnedShoe, 1).current_mileage == mileage_after


def test_preserve_policy_holds_total_when_offset_covers_backfill(db):
    # starting offset (100) already represents this history; preserve keeps the
    # displayed total put and reduces the offset by the backfilled km.
    _shoe(db, 1, starting=100.0)
    _strava(db, 5001, D, 10.0, gear="Adidas Evo SL")
    _strava(db, 5002, D + timedelta(days=2), 12.0, gear="Adidas Evo SL")
    _map(db, "Adidas Evo SL", 1)
    db.commit()

    bf.execute_backfill(db, mileage_policy=bf.POLICY_PRESERVE)
    shoe = db.get(OwnedShoe, 1)
    assert shoe.current_mileage == 100.0          # unchanged total
    assert shoe.starting_mileage == 78.0          # 100 - (10 + 12)
    # invariant: current == starting_offset + sum(runs)
    total_runs = db.query(ShoeRun).filter(ShoeRun.owned_shoe_id == 1).count()
    assert total_runs == 2


def test_add_policy_double_counts(db):
    _shoe(db, 1, starting=100.0)
    _strava(db, 5001, D, 10.0, gear="Adidas Evo SL")
    _map(db, "Adidas Evo SL", 1)
    db.commit()

    bf.execute_backfill(db, mileage_policy=bf.POLICY_ADD)
    assert db.get(OwnedShoe, 1).current_mileage == 110.0
