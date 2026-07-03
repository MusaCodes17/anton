"""
Seed strava_gear_mappings from imported activities (§3).

1. Reads DISTINCT gear_name from strava_activities.
2. Auto-matches each against owned_shoes (all statuses) by normalized name.
3. Prints the proposed mapping table and requires confirmation (or --yes).
4. Writes matched gear -> owned_shoe_id; ambiguous/unmatched are written with
   owned_shoe_id = NULL so they still exist as rows to resolve by hand.
5. Idempotent: an EXISTING mapping (matched or NULL) is never overwritten by
   the auto-matcher. Use --map to resolve a NULL by hand (that DOES overwrite).

Manual resolution:
    python -m app.scripts.seed_gear_mappings --map "PUMA DNE3=20" --map "Adidas Evo SL=3"

Each --map takes "Exact Gear Name=owned_shoe_id"; it upserts that one mapping.
"""
import argparse
import sys

from app.database import SessionLocal
from app.models.models import OwnedShoe, StravaActivity, StravaGearMapping
from app.services.strava_gear import ShoeLike, auto_match


def _distinct_gear(db) -> list[str]:
    rows = (
        db.query(StravaActivity.gear_name)
        .filter(StravaActivity.gear_name.isnot(None))
        .distinct()
        .order_by(StravaActivity.gear_name)
        .all()
    )
    return [r[0] for r in rows]


def _shoe_label(shoe: OwnedShoe) -> str:
    nick = f" ({shoe.nickname})" if shoe.nickname else ""
    return f"[{shoe.id}] {shoe.brand} {shoe.model}{nick} · {shoe.status}"


def _apply_manual(db, pairs: list[str]) -> int:
    """Upsert explicit gear=shoe_id mappings. Returns count applied."""
    applied = 0
    for pair in pairs:
        if "=" not in pair:
            print(f"  skip (bad format, need 'Gear=id'): {pair!r}", file=sys.stderr)
            continue
        gear, _, raw_id = pair.rpartition("=")
        gear = gear.strip()
        try:
            shoe_id = int(raw_id.strip())
        except ValueError:
            print(f"  skip (bad id): {pair!r}", file=sys.stderr)
            continue
        shoe = db.query(OwnedShoe).filter(OwnedShoe.id == shoe_id).first()
        if not shoe:
            print(f"  skip (no owned shoe #{shoe_id}): {pair!r}", file=sys.stderr)
            continue
        mapping = db.query(StravaGearMapping).filter(StravaGearMapping.gear_name == gear).first()
        if mapping is None:
            mapping = StravaGearMapping(gear_name=gear, owned_shoe_id=shoe_id)
            db.add(mapping)
        else:
            mapping.owned_shoe_id = shoe_id
        print(f"  mapped {gear!r} -> {_shoe_label(shoe)}")
        applied += 1
    db.commit()
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Strava gear -> owned shoe mappings")
    parser.add_argument("--yes", action="store_true", help="Write without interactive confirmation")
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="GEAR=ID",
        help="Manually resolve one mapping, e.g. --map 'PUMA DNE3=20' (repeatable)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # Manual resolution mode: apply and exit.
        if args.map:
            print("Applying manual mappings:")
            n = _apply_manual(db, args.map)
            print(f"Done — {n} mapping(s) applied.")
            return 0

        gear_names = _distinct_gear(db)
        shoes = db.query(OwnedShoe).all()
        shoe_likes = [ShoeLike(id=s.id, brand=s.brand, model=s.model, nickname=s.nickname) for s in shoes]
        shoes_by_id = {s.id: s for s in shoes}
        existing = {m.gear_name: m for m in db.query(StravaGearMapping).all()}

        result = auto_match(gear_names, shoe_likes)

        print(f"Found {len(gear_names)} distinct gear names, {len(shoes)} owned shoes.\n")
        print("Proposed mappings (auto-matched):")
        for gear in gear_names:
            if gear in existing:
                cur = existing[gear]
                tgt = shoes_by_id.get(cur.owned_shoe_id)
                state = _shoe_label(tgt) if tgt else "NULL"
                print(f"  = {gear!r:40} already mapped -> {state} (kept)")
            elif gear in result.matched:
                print(f"  ✓ {gear!r:40} -> {_shoe_label(shoes_by_id[result.matched[gear]])}")
            elif gear in result.ambiguous:
                cands = ", ".join(_shoe_label(shoes_by_id[i]) for i in result.ambiguous[gear])
                print(f"  ? {gear!r:40} AMBIGUOUS -> NULL  (candidates: {cands})")
            else:
                print(f"  ✗ {gear!r:40} UNMATCHED -> NULL")

        to_write_matched = {g: sid for g, sid in result.matched.items() if g not in existing}
        to_write_null = [
            g for g in gear_names
            if g not in existing and (g in result.ambiguous or g in result.unmatched)
        ]

        print(
            f"\nWill write {len(to_write_matched)} matched + {len(to_write_null)} NULL "
            f"placeholder(s); {len(existing)} existing kept untouched."
        )
        if to_write_null:
            print("Resolve the NULLs afterward with, e.g.:")
            for g in to_write_null:
                print(f"    python -m app.scripts.seed_gear_mappings --map \"{g}=<owned_shoe_id>\"")

        if not args.yes:
            reply = input("\nWrite these mappings? [y/N] ").strip().lower()
            if reply not in ("y", "yes"):
                print("Aborted — nothing written.")
                return 0

        for gear, sid in to_write_matched.items():
            db.add(StravaGearMapping(gear_name=gear, owned_shoe_id=sid))
        for gear in to_write_null:
            db.add(StravaGearMapping(gear_name=gear, owned_shoe_id=None))
        db.commit()

        print(f"\nWrote {len(to_write_matched)} matched + {len(to_write_null)} NULL mapping(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
