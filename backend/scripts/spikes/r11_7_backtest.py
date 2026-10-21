"""R11.7 spike (throwaway, read-only): backtest finish-time estimators against
past marathons and halves, using only evidence dated before each race.
Not imported by the app.

Usage (on a COPY of the DB, already at alembic head):
    cd backend && venv/bin/python scripts/spikes/r11_7_backtest.py --db /path/to/COPY.db

Read-only: the DB is opened with SQLite `mode=ro` (any write would raise), only
`races_svc.race_entries` (no prune) and `strava_stats.personal_bests` are used.

Method
- Scored: completed marathons (>= 30 km class) and halves (15-30 km class) with a
  result_time_s whose recorded distance is within 5% of the nominal distance and
  whose pace is plausible. DNF races and mismatched rows are listed, not scored.
- Evidence "as of" = the day before the race. Window = the last N weeks
  (race_advisor.RECENT_EFFORT_WEEKS = 8 primary, 12 sensitivity), built exactly as
  race_readiness builds it: [as_of - N weeks + 1 day, as_of].
- (a)  Riegel T2 = T1 * (D2/D1)^k, k = 1.06;  (a') k = 1.08.  D2 = the nominal race
       distance (42.195 / 21.0975 km); D1 = the evidence's own distance_km.
  "Best available" = longest source band >= 10 km and <= the race distance
  (race PB or best effort alike); within the band the faster Riegel time wins;
  if no source >= 10 km exists, the longest shorter one (flagged).
- (b)  Key-effort pace x race distance: best effort at RACE_CLASSES.key_effort
       (marathon -> half, half -> 10k).
- (c)  durability adjustment: not computable (R11.6) - not attempted.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
from datetime import date, timedelta

# --- read-only wiring: must happen before importing app.database --------------
_ap = argparse.ArgumentParser()
_ap.add_argument("--db", required=True, help="path to a COPY of shoe_deals.db at alembic head")
_ap.add_argument("--today", default="2026-10-20")
ARGS = _ap.parse_args()
DB_PATH = os.path.abspath(ARGS.db)
os.environ["DATABASE_URL"] = f"sqlite:///file:{DB_PATH}?mode=ro&uri=true"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models.models import Activity, AthleteMetric  # noqa: E402
from app.services import race_advisor, strava_stats  # noqa: E402
from app.services import races as races_svc  # noqa: E402

KS = (1.06, 1.08)
NOMINAL_KM = {"marathon": 42.195, "half": 21.0975}
SAME_DIST_TOL = 1.01     # a prior half (21.10 km) is a valid source for a half (21.0975 km)
INFORMAL = ("random Tuesday",)   # scored, but titled as a casual run - summarised with and without
DIST_TOL = 0.05          # recorded distance must be within 5% of nominal to count as that race
PACE_RANGE = (150, 480)  # plausible s/km for a race result (2:30-8:00/km)
SOURCE_BANDS = ("5k", "10k", "half", "full")
BAND_ORDER = {b: i for i, b in enumerate(SOURCE_BANDS)}
WINDOWS = (race_advisor.RECENT_EFFORT_WEEKS, 12)


def hms(s):
    if s is None:
        return "-"
    s = int(round(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def mmss(s):
    s = int(round(abs(s)))
    return f"{s // 60}:{s % 60:02d}"


def signed(s):
    return f"{'+' if s >= 0 else '-'}{mmss(s)}"


def riegel(t1, d1, d2, k):
    return t1 * (d2 / d1) ** k


def evidence(db, as_of, weeks, race_km):
    """Sources dated <= as_of inside the window. One dict per record."""
    res = strava_stats.personal_bests(db, date_from=as_of - timedelta(weeks=weeks) + timedelta(days=1), date_to=as_of)
    out = []
    for kind, lst in (("race_pb", res.race_pbs), ("best_effort", res.best_efforts)):
        for p in lst:
            if p.band not in BAND_ORDER:
                continue
            out.append(dict(kind=kind, band=p.band, dist=p.distance_km, time_s=p.total_time_s,
                            date=date.fromisoformat(p.run_date), age=(as_of - date.fromisoformat(p.run_date)).days,
                            segment=p.segment, run_km=p.run_distance_km, activity_id=p.activity_id))
    return out


def best_available(sources, race_km, k):
    """(source, predicted_s, flag). Longest band >= 10 km and < race distance (the
    race's own distance is allowed only for a half-length source before a marathon)."""
    usable = [s for s in sources if s["dist"] <= race_km * SAME_DIST_TOL]
    if not usable:
        return None, None, "none"
    long_enough = [s for s in usable if s["dist"] >= 9.5]
    pool, flag = (long_enough, "ok") if long_enough else (usable, "short-only")
    top = max(BAND_ORDER[s["band"]] for s in pool)
    cand = [s for s in pool if BAND_ORDER[s["band"]] == top]
    src = min(cand, key=lambda s: riegel(s["time_s"], s["dist"], race_km, k))
    return src, riegel(src["time_s"], src["dist"], race_km, k), flag


def per_band(sources, band, race_km, k):
    cand = [s for s in sources if s["band"] == band and s["dist"] <= race_km * SAME_DIST_TOL]
    if not cand:
        return None, None
    src = min(cand, key=lambda s: riegel(s["time_s"], s["dist"], race_km, k))
    return src, riegel(src["time_s"], src["dist"], race_km, k)


def key_effort(db, as_of, weeks, race_km, label):
    res = strava_stats.personal_bests(db, date_from=as_of - timedelta(weeks=weeks) + timedelta(days=1), date_to=as_of)
    e = next((p for p in res.best_efforts if p.band == label), None)
    if not e:
        return None, None
    pace = e.total_time_s / e.distance_km
    src = dict(kind="best_effort", band=label, dist=e.distance_km, time_s=e.total_time_s,
               date=date.fromisoformat(e.run_date), age=(as_of - date.fromisoformat(e.run_date)).days,
               segment=e.segment, activity_id=e.activity_id)
    return src, pace * race_km


def grade(sources, race_km, as_of, k=1.06):
    """PROPOSED evidence-grade rules (see the report). Returns (grade, reasons)."""
    usable = [s for s in sources if s["dist"] <= race_km * SAME_DIST_TOL]
    long_src = [s for s in usable if s["dist"] >= 9.5]
    if not usable:
        return "none", ["no effort or race of 5 km+ in the window"]
    if not long_src:
        return "thin", ["only sub-10 km evidence in the window"]
    reach = max(s["dist"] for s in long_src) / race_km
    top = max(long_src, key=lambda s: s["dist"])
    # agreement: spread of per-band best equivalents across 5k/10k/half sources
    eq = {}
    for s in usable:
        t = riegel(s["time_s"], s["dist"], race_km, k)
        eq[s["band"]] = min(eq.get(s["band"], t), t)
    spread = (max(eq.values()) - min(eq.values())) / min(eq.values()) if len(eq) >= 2 else None
    reasons = [f"longest source {top['band']} ({top['dist']:.1f} km = {reach:.0%} of race), {top['age']} d old",
               f"{len(eq)} distinct bands" + (f", spread {spread:.1%}" if spread is not None else "")]
    if reach >= 0.45 and top["age"] <= 42 and len(eq) >= 2 and spread is not None and spread <= 0.04:
        return "strong", reasons
    if spread is not None and spread > 0.10:
        return "thin", reasons + ["sources disagree by more than 10%"]
    if top["age"] <= 56:
        return "moderate", reasons
    return "thin", reasons


def main():
    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})
    db = sessionmaker(bind=engine)()
    today = date.fromisoformat(ARGS.today)
    try:
        run(db, today)
    finally:
        db.rollback()
        db.close()


def run(db, today):
    entries = races_svc.race_entries(db, today)
    scored, excluded, ignored = [], [], []
    for e in entries:
        rd = e.race_date
        cls = race_advisor.race_class_for(e.distance_km)
        act = db.get(Activity, e.activity_id) if e.activity_id else None
        act_km = act.distance_km if act else None
        label = f"{e.name} {rd} ({e.status}, {e.distance_km} km{'' if act_km is None else f', linked run {act_km:.2f} km'})"
        if rd >= today and e.status != "completed":
            continue
        if cls is None or cls.name not in NOMINAL_KM:
            ignored.append(label)
            continue
        nominal = NOMINAL_KM[cls.name]
        if e.status == "dnf":
            excluded.append((label, "DNF - not a result"))
            continue
        if e.status != "completed" or not e.result_time_s:
            excluded.append((label, f"status {e.status}, no result"))
            continue
        rec_km = act_km or e.distance_km
        if abs(rec_km / nominal - 1) > DIST_TOL:
            excluded.append((label, f"recorded {rec_km:.2f} km is not a {cls.name} ({nominal} km): result {hms(e.result_time_s)} is not a {cls.name} time"))
            continue
        pace = e.result_time_s / rec_km
        if not (PACE_RANGE[0] <= pace <= PACE_RANGE[1]):
            excluded.append((label, f"implausible pace {pace:.0f} s/km"))
            continue
        stopped = (act.elapsed_time_s / act.moving_time_s - 1) if act and act.moving_time_s and act.elapsed_time_s else 0.0
        scored.append(dict(entry=e, cls=cls, nominal=nominal, actual=e.result_time_s, date=rd,
                           name=e.name, target=e.target_time_s, rec_km=rec_km, stopped=stopped))
    scored.sort(key=lambda r: r["date"])

    print(f"DB copy: {DB_PATH}   today={today}   Riegel k={KS}   windows={WINDOWS} weeks")
    print(f"\nScored: {len(scored)}  (" + ", ".join(f"{c}: {sum(1 for r in scored if r['cls'].name == c)}" for c in NOMINAL_KM) + ")")
    print("Scored rows (elapsed-vs-moving gap = stopped time inside the result):")
    for r in scored:
        print(f"  - {r['name']} {r['date']} {r['cls'].name} {r['rec_km']:.2f} km result {hms(r['actual'])}  stopped-time gap {r['stopped']:+.1%}")
    print("Excluded rows:")
    for lab, why in excluded:
        print(f"  - {lab}: {why}")
    print(f"Ignored (outside marathon/half classes): {len(ignored)} rows")
    for lab in ignored:
        print(f"  - {lab}")

    results = {w: [] for w in WINDOWS}  # rows: dicts of estimator -> predicted
    for r in scored:
        as_of = r["date"] - timedelta(days=1)
        for w in WINDOWS:
            src_all = evidence(db, as_of, w, r["nominal"])
            row = dict(race=r, window=w, as_of=as_of, sources=src_all, preds={}, used={})
            for k in KS:
                s, p, flag = best_available(src_all, r["nominal"], k)
                row["preds"][f"a{k}"] = p
                row["used"][f"a{k}"] = (s, flag)
                for band in ("5k", "10k", "half"):
                    s, p = per_band(src_all, band, r["nominal"], k)
                    row["preds"][f"a{k}:{band}"] = p
                    row["used"][f"a{k}:{band}"] = (s, "ok")
            # (a-fast) sensitivity: the FASTEST equivalent among the 10k/half sources (all
            # 5k/10k/half for "a-fast5") - "best demonstrated", since an easy run's segment can
            # only understate fitness. Added after seeing that "longest band" is dominated by
            # easy long-run segments; it is a post-hoc alternative, not the pre-registered rule.
            for key, bands in (("afast", ("10k", "half")), ("afast5", ("5k", "10k", "half"))):
                cands = [per_band(src_all, b, r["nominal"], 1.06) for b in bands]
                cands = [(sx, px) for sx, px in cands if px is not None]
                if cands:
                    sx, px = min(cands, key=lambda c: c[1])
                    row["preds"][key], row["used"][key] = px, (sx, "ok")
                else:
                    row["preds"][key], row["used"][key] = None, (None, "")
            s, p = key_effort(db, as_of, w, r["nominal"], r["cls"].key_effort)
            row["preds"]["b"] = p
            row["used"]["b"] = (s, "ok")
            row["grade"] = grade(src_all, r["nominal"], as_of)
            results[w].append(row)

    for w in WINDOWS:
        print(f"\n================ WINDOW {w} WEEKS ================")
        for row in results[w]:
            r = row["race"]
            print(f"\n{r['name']} {r['date']}  {r['cls'].name}  actual {hms(r['actual'])}  target {hms(r['target']) if r['target'] else '-'}"
                  f"  (as of {row['as_of']}, nominal {r['nominal']} km)")
            print("  evidence:")
            for s in sorted(row["sources"], key=lambda s: (BAND_ORDER[s["band"]], s["kind"])):
                print(f"    {s['kind']:12s} {s['band']:5s} {s['dist']:6.2f} km  {hms(s['time_s'])}  {s['date']}  age {s['age']:3d} d  "
                      f"{'segment of ' + str(s['run_km']) + ' km run' if s['segment'] else 'full run'}")
            for key in ("a1.06", "a1.08", "a1.06:5k", "a1.06:10k", "a1.06:half", "afast", "afast5", "b"):
                p = row["preds"].get(key)
                s, flag = row["used"].get(key, (None, ""))
                if p is None:
                    print(f"  {key:11s} n/a")
                    continue
                err = p - r["actual"]
                print(f"  {key:11s} pred {hms(p)}  err {signed(err)} ({err / r['actual']:+.1%})  from {s['kind']} {s['band']} "
                      f"{s['dist']:.1f} km {s['date']} age {s['age']} d {'segment' if s['segment'] else 'full run'}"
                      f"{'  [' + flag + ']' if flag not in ('ok',) else ''}")
            print(f"  grade (proposed): {row['grade'][0]} - {'; '.join(row['grade'][1])}")

        # summary
        print(f"\n--- summary, window {w} wk (error = pred - actual) ---")
        keys = ["a1.06", "a1.08", "a1.06:5k", "a1.06:10k", "a1.06:half", "a1.08:10k", "a1.08:half", "afast", "afast5", "b"]
        for key in keys:
            rows = [(row["preds"][key], row["race"]) for row in results[w] if row["preds"].get(key) is not None]
            if not rows:
                print(f"  {key:11s} n=0")
                continue
            errs = [(p - r["actual"], (p - r["actual"]) / r["actual"], r) for p, r in rows]
            for scope in ("all", "marathon", "half", "no_informal"):
                sel = [x for x in errs if scope == "all" or x[2]["cls"].name == scope
                       or (scope == "no_informal" and not any(t in x[2]["name"] for t in INFORMAL))]
                if not sel:
                    continue
                bias = statistics.mean(x[1] for x in sel)
                mape = statistics.mean(abs(x[1]) for x in sel)
                worst = max(sel, key=lambda x: abs(x[1]))
                print(f"  {key:11s} {scope:8s} n={len(sel)}  bias {bias:+.1%} ({signed(statistics.mean(x[0] for x in sel))})  "
                      f"MAPE {mape:.1%}  worst {worst[1]:+.1%} ({signed(worst[0])}, {worst[2]['name']})  "
                      f"within +/-3min: {sum(abs(x[0]) <= 180 for x in sel)}/{len(sel)}  within 2%: {sum(abs(x[1]) <= 0.02 for x in sel)}/{len(sel)}  within 5%: {sum(abs(x[1]) <= 0.05 for x in sel)}/{len(sel)}")

        # leave-one-out range for the best-available estimators
        for key in ("a1.06", "a1.08", "afast"):
            print(f"\n--- range via leave-one-out, estimator {key}, window {w} wk "
                  "(band = pred x (1 +/- max |% error| of the OTHER races)) ---")
            rows = [row for row in results[w] if row["preds"].get(key) is not None]
            for row in rows:
                others = [abs((o["preds"][key] - o["race"]["actual"]) / o["race"]["actual"]) for o in rows if o is not row]
                if not others:
                    print(f"  {row['race']['name']}: no other races to calibrate on")
                    continue
                band = max(others)
                p, a = row["preds"][key], row["race"]["actual"]
                lo, hi = p * (1 - band), p * (1 + band)
                print(f"  {row['race']['name']:22s} {hms(lo)} - {hms(hi)} (+/-{band:.1%}, {mmss(p * band)})  "
                      f"actual {hms(a)}  {'INSIDE' if lo <= a <= hi else 'OUTSIDE'}")

    # ---- the next race / today ---------------------------------------------------
    print("\n================ NEXT RACE (informational) ================")
    upcoming = [e for e in entries if e.race_date >= today and e.status != "completed" and e.status != "dnf"]
    print(f"upcoming planned races as of {today}: {[(e.name, str(e.race_date), e.distance_km, e.status) for e in upcoming] or 'none'}")
    for km, name in ((42.195, "marathon"), (21.0975, "half")):
        for w in WINDOWS:
            src_all = evidence(db, today, w, km)
            print(f"\nIf a {name} were run after {today} (evidence window {w} wk ending today):")
            for s in sorted(src_all, key=lambda s: (BAND_ORDER[s["band"]], s["kind"])):
                print(f"    {s['kind']:12s} {s['band']:5s} {s['dist']:6.2f} km  {hms(s['time_s'])}  {s['date']}  age {s['age']:3d} d  "
                      f"{'segment' if s['segment'] else 'full run'}")
            for k in KS:
                s, p, flag = best_available(src_all, km, k)
                if p:
                    print(f"  a(k={k})  {hms(p)}  from {s['kind']} {s['band']} {s['date']} age {s['age']} d [{flag}]")
                for band in ("5k", "10k", "half"):
                    sb, pb = per_band(src_all, band, km, k)
                    if pb and k == 1.06:
                        print(f"     per-source {band:5s} {hms(pb)}")
            cls = race_advisor.race_class_for(km)
            s, p = key_effort(db, today, w, km, cls.key_effort)
            print(f"  b ({cls.key_effort} pace x distance)  {hms(p) if p else 'n/a'}")
            print(f"  grade (proposed): {grade(src_all, km, today)[0]} - {'; '.join(grade(src_all, km, today)[1])}")

    snaps = db.query(AthleteMetric).order_by(AthleteMetric.captured_at.asc()).all()
    print("\nCOROS fitness snapshots (athlete_metrics) with race_predictions:")
    for sn in snaps:
        if sn.race_predictions:
            rp = sn.race_predictions
            print(f"  {sn.captured_at}  half {hms(rp.get('21.0975'))}  full {hms(rp.get('42.195'))}  10k {hms(rp.get('10.0'))}")
    print("Scored races earlier than the first snapshot cannot be backtested against COROS:")
    first = snaps[0].captured_at.date() if snaps else None
    for r in scored:
        prior = [s for s in snaps if s.race_predictions and s.captured_at.date() < r["date"]]
        if prior:
            rp = prior[-1].race_predictions.get(str(r["nominal"]) if r["nominal"] != 21.0975 else "21.0975") or prior[-1].race_predictions.get("42.195")
            key = "42.195" if r["cls"].name == "marathon" else "21.0975"
            p = prior[-1].race_predictions.get(key)
            print(f"  {r['name']} {r['date']}: snapshot {prior[-1].captured_at.date()} says {hms(p)} vs actual {hms(r['actual'])} "
                  f"({signed(p - r['actual'])}, {(p - r['actual']) / r['actual']:+.1%})")
        else:
            print(f"  {r['name']} {r['date']}: no snapshot before the race (first snapshot {first})")


if __name__ == "__main__":
    main()
