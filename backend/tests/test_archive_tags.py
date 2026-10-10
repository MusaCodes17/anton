"""R5.5.3 — reviewed archive tag backfill: plan is read-only, never overwrites."""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.models import Activity
from app.scripts import infer_archive_tags
from app.services import archive_tags as svc


def _act(db, name, *, source="strava", type_="Run", tag=None, km=5.0, secs=1200, d=date(2023, 5, 14)):
    a = Activity(source=source, activity_type=type_, name=name, run_date=d, distance_km=km,
                 moving_time_s=secs, elapsed_time_s=secs, activity_tag=tag)
    db.add(a)
    db.commit()
    return a


def _tags(db):
    return {a.id: a.activity_tag for a in db.query(Activity)}


def test_plan_only_includes_untagged_strava_runs(db):
    ok = _act(db, "Easy jog")
    _act(db, "Easy jog tagged", tag="Tempo")
    _act(db, "Easy ride", type_="Ride")
    _act(db, "Easy coros", source="coros")
    _act(db, "Morning run")
    plan = svc.plan_archive_tags(db)
    assert [s.activity_id for s in plan.suggestions] == [ok.id]
    assert plan.by_tag == {"Easy": 1}
    assert plan.untouched == 1
    assert plan.steady_runs_removed == 0


def test_plan_writes_nothing_and_reports_new_race_pb(db):
    race = _act(db, "Yamajo 5K Race", km=5.0, secs=1022)
    _act(db, "Long run Sunday", km=20.0, secs=6000)
    before = _tags(db)
    plan = svc.plan_archive_tags(db)
    assert _tags(db) == before
    db.rollback()
    assert _tags(db) == before          # nothing pending or committed
    assert plan.steady_runs_removed == 1   # Race leaves the steady pool; Long Run stays
    assert len(plan.race_pbs_added) == 1
    assert plan.race_pbs_added[0].startswith("5k: none → 17:02 (2023-05-14, 'Yamajo 5K Race')")
    assert plan.race_pbs_changed == []
    assert race.activity_tag is None


def test_plan_reports_changed_pb_and_steady_removals(db):
    _act(db, "Official race", tag="Race", km=5.0, secs=1100)
    _act(db, "Faster race", km=5.0, secs=1000, d=date(2024, 1, 2))
    plan = svc.plan_archive_tags(db)
    assert plan.race_pbs_added == []
    assert len(plan.race_pbs_changed) == 1 and "18:20" in plan.race_pbs_changed[0] and "16:40" in plan.race_pbs_changed[0]
    assert plan.steady_runs_removed == 1   # Race is not a steady tag


def test_apply_writes_planned_and_skips_runner_tagged(db):
    a = _act(db, "Easy one")
    b = _act(db, "Tempo thing", d=date(2023, 6, 1))
    plan = svc.plan_archive_tags(db)
    b.activity_tag = "Workout"           # runner tags between plan and apply
    db.commit()
    assert svc.apply_archive_tags(db, plan) == 1
    assert _tags(db) == {a.id: "Easy", b.id: "Workout"}


def test_cli_dry_run_then_apply(tmp_path, capsys):
    url = f"sqlite:///{tmp_path / 't.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    _act(s, "Easy jog")
    s.close()

    assert infer_archive_tags.main(["--database-url", url]) == 0
    out = capsys.readouterr().out
    assert "Easy jog → Easy" in out and "dry run" in out
    s = sessionmaker(bind=engine)()
    assert s.query(Activity).one().activity_tag is None

    assert infer_archive_tags.main(["--database-url", url, "--apply"]) == 0
    s.expire_all()
    assert s.query(Activity).one().activity_tag == "Easy"
    s.close()
