"""R11.6 spike (throwaway, read-only): can activity_best_efforts answer
"did the long runs finish fast"?  Not imported by the app.

Usage: python r11_6_fast_finish.py --db /path/to/COPY_of_shoe_deals.db

Block = 16 Monday-aligned weeks ending with race week, up to the day before the
race (race_advisor.block_window). Long run = activity >= 28 km, running only.
Segment pace = elapsed_s / segment_km (best-effort timer time); run pace =
moving_time_s / distance_km, so they differ slightly when the run had stops.
"""
import argparse
import sqlite3
from datetime import date, timedelta

LONG_KM = 28.0
BLOCK_WEEKS = 16
RUN_TYPES = ("Run", "Trail Run", "Virtual Run", "run", "running", "Running")


def pace(s):
    if s is None:
        return "-"
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def delta(s):
    if s is None:
        return "-"
    s = int(round(s))
    return f"{'+' if s > 0 else '-' if s < 0 else ''}{abs(s)}s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    a = ap.parse_args()
    c = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row

    races = {}
    for r in c.execute("select * from planned_races where distance_km>=30 and status in ('completed','dnf')"):
        races[r["race_date"]] = dict(name=r["name"], date=r["race_date"], target=r["target_time_s"],
                                     dist=r["distance_km"], act=r["activity_id"], plan=True)
    linked = {v["act"] for v in races.values() if v["act"]}
    for r in c.execute("select * from activities where activity_tag='Race' and distance_km>=30"):
        if r["id"] not in linked:
            races[r["run_date"]] = dict(name=r["name"], date=r["run_date"], target=None,
                                        dist=r["distance_km"], act=r["id"], plan=False)
    chosen = sorted(races.values(), key=lambda x: x["date"])[-3:]

    print(f"activity types in DB: {[r[0] for r in c.execute('select distinct activity_type from activities')]}")
    for rc in chosen:
        rd = date.fromisoformat(rc["date"])
        start = rd - timedelta(days=rd.weekday()) - timedelta(weeks=BLOCK_WEEKS - 1)
        end = rd - timedelta(days=1)
        tp = rc["target"] / rc["dist"] if rc["target"] else None
        print(f"\n== {rc['name']} {rc['date']}  block {start}..{end}  target pace {pace(tp)}"
              f"  (plan row: {rc['plan']}, linked activity {rc['act']})")
        print("date        id    km    avg   | 5k: off%  end%  pace  vs avg  vs tgt | 10k: off%  end%  pace  vs avg  vs tgt | note")
        rows = c.execute(
            "select * from activities where run_date between ? and ? and distance_km>=? "
            "and (activity_type is null or lower(activity_type) like '%run%') order by run_date",
            (start.isoformat(), end.isoformat(), LONG_KM)).fetchall()
        n_seg = 0
        for r in rows:
            km = r["distance_km"]
            avg = r["moving_time_s"] / km
            parts = []
            have = False
            for lab, L in (("5k", 5000), ("10k", 10000)):
                be = c.execute("select * from activity_best_efforts where activity_id=? and distance_label=?",
                               (r["id"], lab)).fetchone()
                if not be:
                    parts.append("      none".ljust(44))
                    continue
                have = True
                sp = be["elapsed_s"] / (L / 1000)
                off = 100 * be["start_offset_m"] / (km * 1000)
                endp = 100 * (be["start_offset_m"] + L) / (km * 1000)
                parts.append(f"{off:5.0f} {endp:5.0f} {pace(sp):>5} {delta(sp - avg):>6} "
                             f"{delta(sp - tp) if tp else '-':>6}")
            n_seg += have
            scan = c.execute("select status from activity_effort_scans where activity_id=?", (r["id"],)).fetchone()
            note = "" if have else f"no segments (scan: {scan[0] if scan else 'never'})"
            if r["activity_tag"]:
                note += f" tag={r['activity_tag']}"
            print(f"{r['run_date']} {r['id']:>5} {km:5.1f} {pace(avg):>5} | " + " | ".join(parts) + f" | {note}")
        print(f"long runs: {len(rows)}, with segments: {n_seg}")


if __name__ == "__main__":
    main()
