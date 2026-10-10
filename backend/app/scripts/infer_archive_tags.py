"""
Suggest `activity_tag` for untagged Strava-archive runs from their names (R5.5.3).

Default is a DRY RUN: prints per-tag counts, the race-PB impact, the steady-run
note and every suggestion, and writes nothing. Re-run with --apply (after
reviewing the output) to write exactly that plan. Existing tags are never
overwritten. The database comes from DATABASE_URL (as the other scripts), or
--database-url.

    python -m app.scripts.infer_archive_tags
    python -m app.scripts.infer_archive_tags --apply

Exit codes: 0 ok, 2 bad arguments.
"""
import argparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import archive_tags as svc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true", help="write the planned tags (default: dry run)")
    p.add_argument("--database-url", help="override DATABASE_URL")
    args = p.parse_args(argv)

    if args.database_url:
        engine = create_engine(args.database_url, connect_args={"check_same_thread": False})
        db = sessionmaker(bind=engine)()
    else:
        from app.database import SessionLocal
        db = SessionLocal()
    try:
        plan = svc.plan_archive_tags(db)
        print(f"{len(plan.suggestions)} untagged archive runs get a tag; {plan.untouched} stay untagged")
        for tag, n in sorted(plan.by_tag.items(), key=lambda kv: -kv[1]):
            print(f"  {tag}: {n}")
        print("Race PBs added:" + ("" if plan.race_pbs_added else " none"))
        for line in plan.race_pbs_added:
            print(f"  {line}")
        print("Race PBs changed:" + ("" if plan.race_pbs_changed else " none"))
        for line in plan.race_pbs_changed:
            print(f"  {line}")
        print(f"{plan.steady_runs_removed} runs would leave the form trend's steady pool "
              "(untagged counts as steady; only Easy/Long Run stay)")
        print("Suggestions:")
        for s in plan.suggestions:
            km = f"{s.distance_km:.1f}" if s.distance_km is not None else "?"
            print(f"  {s.run_date}  {km:>5} km  {s.name} → {s.tag}")
        if args.apply:
            print(f"applied: {svc.apply_archive_tags(db, plan)} runs tagged")
        else:
            print("dry run — nothing written (use --apply to write this plan)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
