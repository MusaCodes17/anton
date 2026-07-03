"""
Strava dedup + backfill runner (§4 / §5).

Dry-run is the DEFAULT and writes nothing — review its report (especially shoe
conflicts, date-shift candidates, and the mileage reconciliation table) before
committing. This is the checkpoint where mistakes are free.

    python -m app.scripts.backfill_strava                      # dry-run report
    python -m app.scripts.backfill_strava --commit             # apply (preserve policy)
    python -m app.scripts.backfill_strava --commit --mileage-policy add
    python -m app.scripts.backfill_strava --commit \
        --mileage-policy preserve \
        --shoe-policy 5=offset-zero --shoe-policy 12=add   # per-shoe overrides

Mileage policies (§5):
  preserve (default) — reduce each shoe's starting_mileage by the backfilled
                       km (floored at 0) so its displayed total stays put while
                       gaining real run rows. Best when starting_mileage already
                       represents this Strava history (the common case here).
  offset-zero        — drop starting_mileage entirely; the runs define the total.
  add                — naively add backfilled km (DOUBLE-COUNTS any history
                       already baked into starting_mileage; only safe for shoes
                       whose starting offset is ~0).
"""
import argparse

from app.database import SessionLocal
from app.services import strava_backfill as bf


def _print_report(report: bf.BackfillReport, policy: str) -> None:
    print("=" * 72)
    print(f"STRAVA BACKFILL — {'COMMITTED' if report.committed else 'DRY RUN (no writes)'}")
    print("=" * 72)

    print(f"\nMatched (link to existing runs):        {len(report.matched)}")
    print(f"  of which shoe conflicts:              {len(report.conflicts)}")
    print(f"Date-shift candidates (manual review):  {len(report.date_shift)}")
    print(f"Ambiguous (manual review):              {len(report.ambiguous)}")
    print(f"Will create (backfill runs):            {len(report.to_create)}")
    print(f"Skipped — gear unmapped:                {len(report.skipped_unmapped)}")
    print(f"Skipped — no gear:                      {len(report.skipped_no_gear)}")

    if report.conflicts:
        print("\n-- Shoe conflicts (COROS/manual assignment kept; gear differs) --")
        for c in report.conflicts:
            print(f"  • {c.detail}")

    if report.date_shift:
        print("\n-- Date-shift candidates (NOT auto-linked; confirm by hand) --")
        for d in report.date_shift:
            print(f"  • {d.detail}")

    if report.ambiguous:
        print("\n-- Ambiguous same-day matches (NOT auto-linked) --")
        for a in report.ambiguous:
            print(f"  • strava {a['strava_activity_id']} ({a['run_date']}, {a['distance_km']}km) "
                  f"→ runs {a['candidate_run_ids']}")

    print("\n-- Backfill runs to create, per shoe --")
    per_shoe: dict[int, int] = {}
    for c in report.to_create:
        per_shoe[c.owned_shoe_id] = per_shoe.get(c.owned_shoe_id, 0) + 1
    for r in report.reconcile:
        print(f"  shoe {r.shoe_id:>2} {r.name:<40} {per_shoe.get(r.shoe_id, 0):>3} runs  "
              f"{r.sum_backfill_km:>7.1f}km")

    print(f"\n-- Mileage reconciliation (policy: {policy}) --")
    print(f"  {'shoe':<42} {'current':>9} {'runs':>8} {'offset':>8} {'+backfill':>9} {'final':>9}  flag")
    for r in report.reconcile:
        flag = "  ⚠ REVIEW" if r.flagged else ""
        name = f"{r.shoe_id} {r.name}"
        print(f"  {name:<42} {r.current_mileage:>9.1f} {r.sum_existing_runs:>8.1f} "
              f"{r.implied_offset:>8.1f} {r.sum_backfill_km:>9.1f} {r.proposed_final:>9.1f}{flag}")

    flagged = [r for r in report.reconcile if r.flagged]
    if flagged and not report.committed:
        print(f"\n  ⚠ {len(flagged)} shoe(s) have a starting offset that overlaps the backfill "
              "period.\n    Under 'preserve' their displayed total is held constant (the offset is\n"
              "    replaced by real runs). Review before committing — §5 forbids auto-resolving\n"
              "    these blindly. Choose --mileage-policy explicitly if 'preserve' is wrong.")


def _parse_shoe_policy(parser: argparse.ArgumentParser, values: list[str]) -> dict[int, str]:
    """Parse repeated --shoe-policy SHOE_ID=POLICY into {shoe_id: policy}."""
    out: dict[int, str] = {}
    for v in values:
        if "=" not in v:
            parser.error(f"--shoe-policy expects SHOE_ID=POLICY, got {v!r}")
        sid_str, policy = v.split("=", 1)
        try:
            sid = int(sid_str)
        except ValueError:
            parser.error(f"--shoe-policy shoe id must be an int, got {sid_str!r}")
        if policy not in bf.MILEAGE_POLICIES:
            parser.error(
                f"--shoe-policy {v!r}: unknown policy {policy!r}; expected one of {bf.MILEAGE_POLICIES}"
            )
        out[sid] = policy
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Strava dedup + backfill")
    parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    parser.add_argument(
        "--mileage-policy",
        choices=bf.MILEAGE_POLICIES,
        default=bf.POLICY_PRESERVE,
        help="How to reconcile stored mileage on commit (default: preserve)",
    )
    parser.add_argument(
        "--shoe-policy",
        action="append",
        default=[],
        metavar="SHOE_ID=POLICY",
        help="Override the global mileage policy for one shoe id (repeatable), "
             "e.g. --shoe-policy 5=offset-zero",
    )
    args = parser.parse_args()
    per_shoe_policies = _parse_shoe_policy(parser, args.shoe_policy)

    db = SessionLocal()
    try:
        if args.commit:
            report = bf.execute_backfill(
                db, mileage_policy=args.mileage_policy, per_shoe_policies=per_shoe_policies
            )
        else:
            report = bf.plan_backfill(
                db, mileage_policy=args.mileage_policy, per_shoe_policies=per_shoe_policies
            )
        _print_report(report, args.mileage_policy)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
