"""
R11.7 — finish-time range with an evidence grade and a live backtest.

The job: answer "what finish time does my recent running support for this
race?" as a RANGE with its own measured error and a grade of the evidence,
never as a single prediction. The point estimate is the fastest Riegel
equivalent of any 10k or half-marathon source (race result or best effort) in
the last EVIDENCE_WEEKS weeks; the range is that estimate widened by the
largest error the same method made on the runner's own past halves and
marathons (the backtest, recomputed live on every call and never stored).

Why this method: the R11.7 spike (docs/spike_r11_7_finish_estimate.md) found
that "longest source wins" is badly biased because best efforts count stretches
of easy long runs, which only understate fitness; taking the fastest equivalent
fixes most of that. That choice, and the THIN_SPREAD line, were made AFTER the
spike's results with n = 6 past races (2 marathons) — a description of this
runner's history, not a calibration. The honest consequence is built in: fewer
than MIN_HISTORY scored past races → no range at all.

Layering: race_advisor imports this module (to attach `estimate` to the
readiness payload), so this module must not import race_advisor. The one value
they share, the evidence window, is mirrored here and pinned by a test.
Read-only; no commits, no writes. Whole-table cost: one `personal_bests` pass
per past race plus one for the race itself — fine at personal scale (a handful
of races).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Activity, AthleteMetric
from app.services import races as races_svc
from app.services import strava_stats

RIEGEL_K = 1.06                   # Riegel exponent T2 = T1 × (D2/D1)^k; the classic 1.06 (k 1.08 scored the same in the spike)
NOMINAL_KM = {"marathon": 42.195, "half": 21.0975}
DIST_TOL = 0.05                   # a distance within 5% of a nominal counts as that race (also classes a planned race)
SAME_DIST_TOL = 1.01              # a source may be up to the race's own distance (a 21.10 km half before a 21.0975 km half)
PACE_RANGE_S_PER_KM = (150, 480)  # plausible race pace, 2:30–8:00/km; outside is a bad record, not a result
# Equals race_advisor.RECENT_EFFORT_WEEKS so the estimate and the readiness key
# effort read the same window; a test asserts they match (no import: see docstring).
EVIDENCE_WEEKS = 8
POINT_BANDS = ("10k", "half")                 # bands that may set the point estimate
GRADE_BANDS = ("5k", "10k", "half", "full")   # bands that count as evidence and for the grade
MIN_HISTORY = 3                   # scored past races needed before a range is shown
THIN_WIDEN = 1.5                  # a thin-evidence range is widened by this factor

# Grade thresholds. STRONG_* come from the spike's pre-stated rules; THIN_SPREAD
# (10%) was chosen after seeing the spike's errors, n = 6, with one race at 10.2%
# — treat it as a description of that history, not a validated cut.
STRONG_REACH = 0.45               # longest 10k+ source must be at least this share of the race distance
STRONG_AGE_DAYS = 42              # ... and at most this old
STRONG_SPREAD = 0.04              # ... with at least two distances agreeing within 4%
THIN_SPREAD = 0.10                # sources disagreeing by more than 10% are thin
MODERATE_AGE_DAYS = 56            # a 10k+ source older than 8 weeks makes the evidence thin

_BAND_ORDER = {b: i for i, b in enumerate(GRADE_BANDS)}
_LONG_BANDS = ("10k", "half", "full")   # "10k+" for the grade rules
_COROS_KEYS = {"marathon": "42.195", "half": "21.0975"}   # athlete_metrics.race_predictions keys


@dataclass
class EstimateSource:
    """One piece of evidence: a race result or a best effort inside the window."""
    kind: str                 # "race_pb" | "best_effort"
    band: str                 # "5k" | "10k" | "half" | "full"
    distance_km: float        # the effort's own distance
    time_s: int
    run_date: str             # ISO date
    age_days: int             # evidence_to − run_date
    activity_id: Optional[int]
    name: Optional[str]
    segment: bool             # a stretch inside a longer run, not the whole run
    equivalent_s: int         # time_s scaled to the race distance with RIEGEL_K
    sets_estimate: bool = False   # this source is the fastest 10k/half equivalent


@dataclass
class BacktestRace:
    """A past race the method was run against, using only evidence before it."""
    name: str
    race_date: str
    race_class: str           # "marathon" | "half"
    actual_s: int
    predicted_s: Optional[int]    # None when the window held no 10k/half evidence
    error_s: Optional[int]        # predicted − actual (positive = predicted slower)
    error_pct: Optional[float]    # error_s / actual_s, a fraction, 4 dp
    grade: Optional[str]


@dataclass
class BacktestSkip:
    name: str
    race_date: str
    reason: str


@dataclass
class FinishEstimate:
    """Finish-time range for a race. `state` says whether a range exists:
    ok | unsupported_distance | insufficient_evidence | insufficient_history;
    `message` names what is missing in plain words when it isn't ok."""
    state: str
    message: Optional[str] = None
    race_class: Optional[str] = None
    race_km: Optional[float] = None       # the nominal km used (the entered km when unsupported)
    riegel_k: float = RIEGEL_K
    window_from: Optional[str] = None     # ISO, inclusive
    window_to: Optional[str] = None
    estimate_s: Optional[int] = None
    low_s: Optional[int] = None
    high_s: Optional[int] = None
    band_pct: Optional[float] = None      # fraction: the largest past |error|, before any thin widening
    grade: Optional[str] = None           # "strong" | "moderate" | "thin"
    grade_reasons: list = field(default_factory=list)
    spread_pct: Optional[float] = None    # how far apart the per-distance equivalents are (fraction)
    target_time_s: Optional[int] = None
    target_position: Optional[str] = None  # target vs [low, high]: "faster" | "inside" | "slower"
    sources: list = field(default_factory=list)            # list[EstimateSource], shortest band first
    backtest: list = field(default_factory=list)           # list[BacktestRace], oldest first
    backtest_skipped: list = field(default_factory=list)   # list[BacktestSkip]
    backtest_n: int = 0
    backtest_mean_abs_pct: Optional[float] = None
    backtest_max_abs_pct: Optional[float] = None
    coros_prediction_s: Optional[int] = None   # COROS's own figure — a separate source, not part of the range
    coros_captured_at: Optional[str] = None
    heuristic: bool = True


@dataclass
class _Evidence:
    """The point estimate and grade for one (race distance, evidence date)."""
    sources: list
    estimate_s: Optional[int]
    grade: Optional[str]
    reasons: list
    spread_pct: Optional[float]
    window_from: date


def _class_for(distance_km: Optional[float]) -> Optional[str]:
    """The nominal race class a distance falls in (within DIST_TOL), else None."""
    if not distance_km:
        return None
    for name, nominal in NOMINAL_KM.items():
        if abs(distance_km / nominal - 1) <= DIST_TOL:
            return name
    return None


def _equivalent_s(time_s: int, distance_km: float, race_km: float) -> float:
    return time_s * (race_km / distance_km) ** RIEGEL_K


def _grade(sources: list, race_km: float) -> tuple[Optional[str], list, Optional[float]]:
    """(grade, reasons, spread) over the usable sources, by the spike's rules.
    strong: longest 10k+ source >= STRONG_REACH of the race and <= STRONG_AGE_DAYS
    old, two or more distances, spread <= STRONG_SPREAD. thin: spread >
    THIN_SPREAD, or the newest 10k+ source older than MODERATE_AGE_DAYS.
    Otherwise moderate. Spread uses the displayed (rounded) equivalents."""
    long_src = [s for s in sources if s.band in _LONG_BANDS]
    if not long_src:
        return None, [], None
    best: dict[str, int] = {}
    for s in sources:
        best[s.band] = min(best.get(s.band, s.equivalent_s), s.equivalent_s)
    spread = (max(best.values()) - min(best.values())) / min(best.values()) if len(best) >= 2 else None

    top = max(long_src, key=lambda s: s.distance_km)
    reach = top.distance_km / race_km
    newest_age = min(s.age_days for s in long_src)
    reasons = [f"Longest source: {top.band} ({top.distance_km:.1f} km, {reach:.0%} of the race), "
               f"{top.age_days} days old"]
    if spread is None:
        reasons.append("Only one distance in the window, so nothing to cross-check")
    elif spread > THIN_SPREAD:
        reasons.append(f"Sources disagree by {spread:.1%} (more than {THIN_SPREAD:.0%})")
    else:
        reasons.append(f"{len(best)} distances agree within {spread:.1%}")
    if newest_age > MODERATE_AGE_DAYS:
        reasons.append(f"Newest 10k+ source is {newest_age} days old (more than {MODERATE_AGE_DAYS})")

    if (reach >= STRONG_REACH and top.age_days <= STRONG_AGE_DAYS
            and spread is not None and spread <= STRONG_SPREAD):
        return "strong", reasons, spread
    if (spread is not None and spread > THIN_SPREAD) or newest_age > MODERATE_AGE_DAYS:
        return "thin", reasons, spread
    return "moderate", reasons, spread


def _evidence(db: Session, *, race_km: float, evidence_to: date) -> _Evidence:
    """Usable sources, point estimate and grade as of `evidence_to`. The one
    evidence function: the live estimate and every backtested race call it."""
    window_from = evidence_to - timedelta(weeks=EVIDENCE_WEEKS) + timedelta(days=1)
    res = strava_stats.personal_bests(db, date_from=window_from, date_to=evidence_to)
    picked = [(kind, p) for kind, lst in (("race_pb", res.race_pbs), ("best_effort", res.best_efforts))
              for p in lst
              if p.band in GRADE_BANDS and p.run_date and p.distance_km <= race_km * SAME_DIST_TOL]
    # race_pbs keep runs flagged exclude_from_analysis (an official result stays a
    # record); the estimate must not use them, so one bad file can't move it.
    ids = [p.activity_id for _, p in picked if p.activity_id is not None]
    excluded = {i for (i,) in db.query(Activity.id).filter(
        Activity.id.in_(ids), Activity.exclude_from_analysis.is_(True))} if ids else set()

    sources = [
        EstimateSource(
            kind=kind, band=p.band, distance_km=p.distance_km, time_s=p.total_time_s,
            run_date=p.run_date, age_days=(evidence_to - date.fromisoformat(p.run_date)).days,
            activity_id=p.activity_id, name=p.name, segment=p.segment,
            equivalent_s=round(_equivalent_s(p.total_time_s, p.distance_km, race_km)),
        )
        for kind, p in picked if p.activity_id not in excluded
    ]
    sources.sort(key=lambda s: (_BAND_ORDER[s.band], s.kind, s.distance_km))

    point = [s for s in sources if s.band in POINT_BANDS]
    if not point:
        return _Evidence(sources, None, None, [], None, window_from)
    fastest = min(point, key=lambda s: _equivalent_s(s.time_s, s.distance_km, race_km))
    fastest.sets_estimate = True
    grade, reasons, spread = _grade(sources, race_km)
    return _Evidence(sources, fastest.equivalent_s, grade, reasons, spread, window_from)


def _backtest(db: Session, *, as_of: date) -> tuple[list, list]:
    """Run the method against every past half and marathon before `as_of`, each
    with evidence from the day before it. Returns (scored+unpredicted races,
    skips), oldest first. Entries not near a half or marathon are ignored
    silently. Live every call — nothing is stored."""
    races: list[BacktestRace] = []
    skipped: list[BacktestSkip] = []
    entries = [e for e in races_svc.race_entries(db, as_of) if e.race_date < as_of]
    for e in sorted(entries, key=lambda e: e.race_date):
        act = db.get(Activity, e.activity_id) if e.activity_id else None
        entry_cls = _class_for(e.distance_km)
        run_cls = _class_for(act.distance_km) if act else None
        cls = run_cls if act else entry_cls
        if entry_cls is None and run_cls is None:
            continue
        when = e.race_date.isoformat()
        if e.status == "dnf":
            skipped.append(BacktestSkip(e.name, when, "DNF — not a result"))
            continue
        if act and run_cls is None:
            skipped.append(BacktestSkip(
                e.name, when, f"Linked run is {act.distance_km or 0:.1f} km, not a {entry_cls}"))
            continue
        cls = cls or entry_cls
        if e.status != "completed" or not e.result_time_s:
            skipped.append(BacktestSkip(e.name, when, "Not completed, or no result time recorded"))
            continue
        km = act.distance_km if act else e.distance_km
        pace = e.result_time_s / km
        if not (PACE_RANGE_S_PER_KM[0] <= pace <= PACE_RANGE_S_PER_KM[1]):
            skipped.append(BacktestSkip(e.name, when, f"Implausible pace ({pace:.0f} s/km)"))
            continue
        if act and act.exclude_from_analysis:
            skipped.append(BacktestSkip(e.name, when, "Linked run is excluded from analysis"))
            continue

        ev = _evidence(db, race_km=NOMINAL_KM[cls], evidence_to=e.race_date - timedelta(days=1))
        err = ev.estimate_s - e.result_time_s if ev.estimate_s is not None else None
        races.append(BacktestRace(
            name=e.name, race_date=when, race_class=cls, actual_s=e.result_time_s,
            predicted_s=ev.estimate_s, error_s=err,
            error_pct=round(err / e.result_time_s, 4) if err is not None else None,
            grade=ev.grade))
    return races, skipped


def _coros_prediction(db: Session, *, race_class: str, evidence_to: date) -> tuple[Optional[int], Optional[str]]:
    """COROS's own race prediction from the latest snapshot captured on or before
    `evidence_to`. A separate source: it is shown beside the range, never in it."""
    key = _COROS_KEYS[race_class]
    for m in db.query(AthleteMetric).order_by(AthleteMetric.captured_at.desc(), AthleteMetric.id.desc()):
        if not m.race_predictions or m.captured_at is None or m.captured_at.date() > evidence_to:
            continue
        value = m.race_predictions.get(key)
        return (round(value), m.captured_at.isoformat()) if value else (None, None)
    return None, None


def finish_estimate(
    db: Session, *, race_distance_km: Optional[float], target_time_s: Optional[int],
    as_of: date, evidence_to: date,
) -> FinishEstimate:
    """
    The finish-time range for a race of `race_distance_km`.

    `evidence_to` is the last day whose runs count (readiness passes its
    block_end); `as_of` bounds which past races the backtest may use. A planned
    race is classed to the nominal marathon/half when within DIST_TOL, and the
    nominal distance (not the entered one) is what sources are scaled to.

    States: unsupported_distance (not near a half or marathon),
    insufficient_evidence (no 10k/half source in the window),
    insufficient_history (fewer than MIN_HISTORY scored past races — estimate
    shown, no range), ok. In `ok`, low/high = estimate × (1 ∓ band), band being
    the largest past |error| (× THIN_WIDEN when the grade is thin). Read-only.
    """
    cls = _class_for(race_distance_km)
    if cls is None:
        return FinishEstimate(
            state="unsupported_distance", race_km=race_distance_km, target_time_s=target_time_s,
            message=("The race has no distance." if not race_distance_km else
                     f"A finish estimate needs a half marathon or marathon; this race is {race_distance_km:g} km."))
    race_km = NOMINAL_KM[cls]
    ev = _evidence(db, race_km=race_km, evidence_to=evidence_to)
    out = FinishEstimate(
        state="ok", race_class=cls, race_km=race_km,
        window_from=ev.window_from.isoformat(), window_to=evidence_to.isoformat(),
        estimate_s=ev.estimate_s, grade=ev.grade, grade_reasons=ev.reasons,
        spread_pct=round(ev.spread_pct, 4) if ev.spread_pct is not None else None,
        target_time_s=target_time_s, sources=ev.sources)
    out.coros_prediction_s, out.coros_captured_at = _coros_prediction(
        db, race_class=cls, evidence_to=evidence_to)

    # Whole-table cost: one personal_bests pass per past race (see module docstring).
    out.backtest, out.backtest_skipped = _backtest(db, as_of=as_of)
    counted = [b for b in out.backtest if b.error_pct is not None]
    out.backtest_n = len(counted)
    if counted:
        abs_pcts = [abs(b.error_pct) for b in counted]
        out.backtest_mean_abs_pct = round(sum(abs_pcts) / len(abs_pcts), 4)
        out.backtest_max_abs_pct = max(abs_pcts)

    if ev.estimate_s is None:
        out.state = "insufficient_evidence"
        out.message = (f"No 10k or half-marathon effort in the last {EVIDENCE_WEEKS} weeks "
                       f"(since {out.window_from}).")
        return out
    if out.backtest_n < MIN_HISTORY:
        out.state = "insufficient_history"
        out.message = (f"Only {out.backtest_n} past race{'' if out.backtest_n == 1 else 's'} "
                       f"to measure this method against (needs {MIN_HISTORY}).")
        return out

    out.band_pct = out.backtest_max_abs_pct
    widen = THIN_WIDEN if ev.grade == "thin" else 1.0
    out.low_s = round(ev.estimate_s * (1 - out.band_pct * widen))
    out.high_s = round(ev.estimate_s * (1 + out.band_pct * widen))
    if target_time_s:
        out.target_position = ("faster" if target_time_s < out.low_s
                               else "slower" if target_time_s > out.high_s else "inside")
    return out
