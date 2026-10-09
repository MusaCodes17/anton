"""
Training trends — the Training page's "Now" answers (R8.4, roadmap §R8.4).

Job: turn run history into short verdicts the runner can read at a glance,
computed once here and served to the page, the MCP tools and Son of Anton
alike (CLAUDE.md §2: correct numbers, once). Read-only; nothing is stored.

R8.4.2 — `load_trend`: "am I building or holding?". Load is measured in
**kilometres**, not COROS training load: only a handful of runs (COROS, since
June 2026) carry `training_load`, while every run since 2018 has a distance.
Nothing here requires an activity tag (7 runs have one).

Scale: one indexed `unified_activities` query over a 35-day window — no
whole-table pass.

R8.4.3 — `form_trend`: "what's my form now?". Three readings and a verdict:

- **Efficiency** across steady runs, in **metres per heartbeat** (distance ÷
  (avg HR × moving minutes)). Steady = untagged or tagged Easy / Long Run,
  ≥ 5 km, avg HR present, elapsed ≤ 1.2× moving time when both are known (a
  run with long stops reads its avg HR over a different clock). Heuristic.
  *Why m/beat and not pace inside a fixed HR band* — both were tried on the
  real archive (2025-01 → 2026-07, 384 steady runs since 2020): month-to-month
  wobble of the monthly median was the same (~2.8–2.9%), but a band throws
  data away — a 140–155 bpm band kept a median 8 of 18 steady runs a month and
  lost months to any minimum, and its result moved with the arbitrary band
  edges (2.7–4.4% wobble across the four bands tried). m/beat uses every
  steady run, needs no per-athlete HR constants, and is nearly independent of
  how hard a run was (r = 0.15 with avg HR, vs. r = −0.76 for pace) — so a
  month with a few harder "steady" runs doesn't fake an improvement. The
  monthly figure is the median, not the mean: 703 of 710 runs are untagged,
  so a race or workout hides among the "steady" runs and must not drag a month.
- **Rolling 90-day best 5k and 10k** vs. the all-time best as of `as_of`, by
  the Records card's Best-efforts rule (strava_stats.best_efforts_among).
- **VO₂ max / threshold line** — the COROS snapshot history (a step series).

The verdict reads efficiency only: the last 6 weeks' steady runs vs. the 12
weeks before. Best efforts depend on whether the runner raced lately and the
VO₂ line is COROS's model, so they ride along as context, not as votes.

Scale: `form_trend` reads the unioned history up to `as_of` (the all-time best
needs it) plus every best-effort row — a whole-history pass, acceptable at
personal scale (~1k runs), as in strava_stats.personal_bests.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.models import AthleteMetric, PlannedRace
from app.services import activities as activities_svc
from app.services import strava_stats
# Private by convention, shared on purpose: the same moving-seconds fallback
# (moving time, else pace × distance) the Volume chart's pace uses. Renaming it
# in activities.py breaks this import too (CLAUDE.md §6 trap).
from app.services.activities import UnifiedActivity, _effective_moving_s
from app.utils.best_efforts import EFFORT_DISTANCES

_TZ = ZoneInfo("America/Toronto")   # run dates are Toronto local dates (CLAUDE.md §6)

# --- load trend thresholds (heuristic) -------------------------------------
# The verdict compares the last 7 days with the average week of the 28 days
# before them (an acute:chronic ratio in km). ±10% is the band where a week is
# ordinary week-to-week noise for a runner holding a steady volume; outside it
# the change is deliberate. These are a heuristic, labelled as such on every
# surface — not a physiological model.
BUILDING_ABOVE = 1.10    # ratio strictly above → "building"; exactly 1.10 is holding
EASING_BELOW = 0.90      # ratio strictly below → "easing"; exactly 0.90 is holding
RATIO_DECIMALS = 2       # ratios are rounded before comparing, so 55/50 reads 1.10, not 1.1000000000000001
ACUTE_DAYS = 7
CHRONIC_DAYS = 28
TAPER_DAYS = 21          # easing within 3 weeks of a planned race reads "taper", not "easing"

VERDICTS = ("building", "holding", "easing", "taper", "no_baseline")


@dataclass
class TaperRace:
    name: str
    race_date: str           # ISO date
    days_to_race: int


@dataclass
class LoadTrend:
    """The "building or holding?" answer for one day.

    `ratio` is last-7-days km over the prior 28 days' average week, rounded to
    2 decimals; None when the prior 28 days have no running (`no_baseline`).
    """
    as_of: str                       # ISO date the windows end on (inclusive)
    verdict: str                     # one of VERDICTS
    ratio: Optional[float]
    last7_km: float
    last7_runs: int
    last7_longest_km: float
    prior_avg_week_km: float         # prior 28 days' km / 4
    prior_longest_km: float
    taper_race: Optional[TaperRace]  # set when the verdict is "taper"
    building_above: float = BUILDING_ABOVE
    easing_below: float = EASING_BELOW
    heuristic: bool = True


def toronto_today() -> date:
    return datetime.now(_TZ).date()


def _next_planned_race_within(db: Session, as_of: date, days: int) -> Optional[PlannedRace]:
    """Soonest still-planned race in [as_of, as_of + days]. A direct read rather
    than races.list_races, which prunes stale plans (a write) as a side effect."""
    return (
        db.query(PlannedRace)
        .filter(
            PlannedRace.status == "planned",
            PlannedRace.race_date >= as_of,
            PlannedRace.race_date <= as_of + timedelta(days=days),
        )
        .order_by(PlannedRace.race_date.asc(), PlannedRace.id.asc())
        .first()
    )


def load_trend(db: Session, *, as_of: Optional[date] = None) -> LoadTrend:
    """Compare the last 7 days (ending `as_of`, inclusive) with the average week
    of the 28 days before them, and give a verdict.

    - ratio > 1.10 → building; 0.90 ≤ ratio ≤ 1.10 → holding; < 0.90 → easing.
    - Easing with a planned race within 21 days of `as_of` (race day included)
      reads "taper" and names the race.
    - No running in the prior 28 days → "no_baseline" (ratio None): there's
      nothing to compare against, whatever the last 7 days hold.

    `as_of` defaults to today in Toronto. The current day counts, so a morning
    read before today's run is a slight undercount — the window is honest about
    what has been run so far. Read-only.
    """
    as_of = as_of or toronto_today()
    acute_start = as_of - timedelta(days=ACUTE_DAYS - 1)
    chronic_start = acute_start - timedelta(days=CHRONIC_DAYS)

    runs = activities_svc.unified_activities(db, date_from=chronic_start, date_to=as_of)
    acute = [r.distance_km or 0.0 for r in runs if r.date >= acute_start]
    chronic = [r.distance_km or 0.0 for r in runs if r.date < acute_start]

    last7_km = sum(acute)
    prior_avg_week = sum(chronic) / (CHRONIC_DAYS / 7)

    ratio: Optional[float] = None
    taper: Optional[TaperRace] = None
    if prior_avg_week <= 0:
        verdict = "no_baseline"
    else:
        ratio = round(last7_km / prior_avg_week, RATIO_DECIMALS)
        if ratio > BUILDING_ABOVE:
            verdict = "building"
        elif ratio < EASING_BELOW:
            verdict = "easing"
            race = _next_planned_race_within(db, as_of, TAPER_DAYS)
            if race is not None:
                verdict = "taper"
                taper = TaperRace(name=race.name, race_date=race.race_date.isoformat(),
                                  days_to_race=(race.race_date - as_of).days)
        else:
            verdict = "holding"

    return LoadTrend(
        as_of=as_of.isoformat(),
        verdict=verdict,
        ratio=ratio,
        last7_km=round(last7_km, 1),
        last7_runs=len(acute),
        last7_longest_km=round(max(acute, default=0.0), 1),
        prior_avg_week_km=round(prior_avg_week, 1),
        prior_longest_km=round(max(chronic, default=0.0), 1),
        taper_race=taper,
    )


# --- form trend (heuristic) -------------------------------------------------
# Steady-run filter: runs whose avg HR says something about aerobic economy.
STEADY_TAGS = (None, "Easy", "Long Run")   # untagged counts: 703 of 710 runs carry no tag
STEADY_MIN_KM = 5.0          # shorter runs are warm-ups/jogs where HR hasn't settled; exactly 5.0 counts
STEADY_MAX_ELAPSED_RATIO = 1.2   # elapsed > 1.2× moving = long stops; exactly 1.2 still counts
# Monthly chart points: a month needs this many steady runs to get a value. The
# archive's 2025–26 months have a median of 18; with 3 or fewer one odd run (a
# race nobody tagged) moves the median several percent — July 2026's 3 runs,
# at a median 163 bpm, read +4% on June. Below it the month keeps its run count
# and gets no value, rather than vanishing.
MIN_MONTH_RUNS = 4
FORM_MONTHS = 12             # the chart: as_of's month (partial) and the 11 before
# Verdict windows: the last 6 weeks' steady runs vs. the 12 weeks before.
# 6 weeks is ~20 steady runs at this runner's usual rate — enough for a stable
# median; a 12-week baseline spans a block, so one odd month doesn't set it.
FORM_RECENT_DAYS = 42
FORM_BASELINE_DAYS = 84
MIN_STEADY_RUNS = 5          # per verdict window; exactly 5 is enough, 4 reads not_enough_data
# ±3%: the archive's monthly median wobbles ~2.9% month to month on average —
# inside that band a change is noise; outside it the runner is genuinely
# covering more (or less) ground per heartbeat. Compared after rounding to 1 dp,
# so exactly +3.0 / −3.0 read "steady".
IMPROVING_ABOVE_PCT = 3.0
SLIPPING_BELOW_PCT = -3.0
FORM_ROLLING_DAYS = 90       # "recent" best efforts: as_of and the 89 days before
FORM_EFFORT_LABELS = ("5k", "10k")
M_PER_BEAT_DECIMALS = 3      # 1.372 m/beat — a 0.1% step, finer than any signal here

FORM_VERDICTS = ("improving", "steady", "slipping", "not_enough_data")


@dataclass
class EfficiencyMonth:
    month: str                         # "2026-07"
    steady_runs: int
    m_per_beat: Optional[float]        # median; None when steady_runs < MIN_MONTH_RUNS


@dataclass
class EffortPoint:
    time_s: int                        # elapsed time over the effort's distance
    pace_s_per_km: int
    distance_km: float                 # the band's for a segment, the whole run's otherwise
    run_date: Optional[str]
    name: Optional[str]
    activity_id: Optional[int]
    segment: bool                      # a stretch inside a longer run (R8.2)


@dataclass
class RollingBest:
    """Best effort at one distance: the last 90 days vs. all time (both ending
    `as_of`). `pct_off_all_time` compares paces — 0.0 when the recent best is
    the all-time best; None when there's no effort in the last 90 days."""
    label: str                         # "5k" | "10k"
    target_km: float
    recent: Optional[EffortPoint]
    all_time: Optional[EffortPoint]
    pct_off_all_time: Optional[float]


@dataclass
class FitnessPoint:
    captured_date: str                 # Toronto local date of the COROS snapshot
    vo2max: Optional[float]
    threshold_pace_s_per_km: Optional[int]
    running_level: Optional[float]


@dataclass
class FormTrend:
    """The "what's my form now?" answer for one day (R8.4.3). A heuristic.

    `change_pct` is the median m/beat of steady runs in the last 42 days vs. the
    84 days before, as a percentage rounded to 1 dp; None when either window
    has fewer than MIN_STEADY_RUNS steady runs (`not_enough_data`).
    """
    as_of: str
    verdict: str                       # one of FORM_VERDICTS
    change_pct: Optional[float]
    recent_m_per_beat: Optional[float]
    recent_steady_runs: int
    baseline_m_per_beat: Optional[float]
    baseline_steady_runs: int
    months: list[EfficiencyMonth]      # oldest first — the card's chart
    best_efforts: list[RollingBest]    # 5k, 10k
    fitness: list[FitnessPoint]        # COROS snapshots up to as_of, oldest first (a step series)
    recent_days: int = FORM_RECENT_DAYS
    baseline_days: int = FORM_BASELINE_DAYS
    min_steady_runs: int = MIN_STEADY_RUNS
    min_month_runs: int = MIN_MONTH_RUNS
    improving_above_pct: float = IMPROVING_ABOVE_PCT
    slipping_below_pct: float = SLIPPING_BELOW_PCT
    heuristic: bool = True


def m_per_beat(r: UnifiedActivity) -> Optional[float]:
    """Metres covered per heartbeat on a steady run, or None when the run isn't
    steady — wrong tag, under 5 km, no avg HR, long stops, or no time at all
    (see the module docstring for the filter and why)."""
    if r.activity_tag not in STEADY_TAGS:
        return None
    if (r.distance_km or 0.0) < STEADY_MIN_KM or not r.avg_hr:
        return None
    if r.elapsed_time_s and r.moving_time_s and r.elapsed_time_s > STEADY_MAX_ELAPSED_RATIO * r.moving_time_s:
        return None
    moving_s = _effective_moving_s(r)
    if not moving_s:
        return None
    return r.distance_km * 1000 / (r.avg_hr * moving_s / 60)


def _effort_point(b: strava_stats.PersonalBest) -> EffortPoint:
    return EffortPoint(
        time_s=b.total_time_s,
        pace_s_per_km=round(b.total_time_s / b.distance_km),
        distance_km=b.distance_km,
        run_date=b.run_date,
        name=b.name,
        activity_id=b.activity_id,
        segment=b.segment,
    )


def _rolling_bests(db: Session, runs: list[UnifiedActivity], as_of: date) -> list[RollingBest]:
    """90-day vs. all-time bests through the Records card's own rule, so the
    all-time figure here is the Records card's figure (as of `as_of`)."""
    window_start = as_of - timedelta(days=FORM_ROLLING_DAYS - 1)
    recent = {b.band: b for b in strava_stats.best_efforts_among(
        db, [r for r in runs if r.date >= window_start], labels=FORM_EFFORT_LABELS)}
    all_time = {b.band: b for b in strava_stats.best_efforts_among(db, runs, labels=FORM_EFFORT_LABELS)}
    metres = dict(EFFORT_DISTANCES)
    out = []
    for label in FORM_EFFORT_LABELS:
        rec, best = recent.get(label), all_time.get(label)
        pct = None
        if rec is not None and best is not None:
            pct = round(((rec.total_time_s / rec.distance_km) / (best.total_time_s / best.distance_km) - 1) * 100, 1)
        out.append(RollingBest(
            label=label,
            target_km=metres[label] / 1000,
            recent=_effort_point(rec) if rec else None,
            all_time=_effort_point(best) if best else None,
            pct_off_all_time=pct,
        ))
    return out


def _captured_date(captured_at: datetime) -> date:
    """Toronto local date of a snapshot. SQLite hands back the server-stamped
    UTC `func.now()` as a naive datetime, so naive means UTC."""
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    return captured_at.astimezone(_TZ).date()


def _fitness_line(db: Session, as_of: date) -> list[FitnessPoint]:
    """Snapshots captured on or before `as_of`, oldest first, one per day (the
    day's last reading). Rows are only written when a value changes (C13), so
    consecutive points are steps. A small table: read whole."""
    by_day: dict[date, AthleteMetric] = {}
    for snap in db.query(AthleteMetric).order_by(AthleteMetric.captured_at.asc(), AthleteMetric.id.asc()):
        if snap.captured_at is None:
            continue
        day = _captured_date(snap.captured_at)
        if day <= as_of:
            by_day[day] = snap
    return [
        FitnessPoint(captured_date=d.isoformat(), vo2max=s.vo2max,
                     threshold_pace_s_per_km=s.threshold_pace_s_per_km, running_level=s.running_level)
        for d, s in sorted(by_day.items())
    ]


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def form_trend(db: Session, *, as_of: Optional[date] = None) -> FormTrend:
    """How is the runner's form as of `as_of` (inclusive; default today in
    Toronto)?

    - Verdict on efficiency (median m/beat of steady runs): the last 42 days
      vs. the 84 days before. change > +3.0% → improving; < −3.0% → slipping;
      otherwise steady (exactly ±3.0 is steady, after rounding to 1 dp). Fewer
      than 5 steady runs in either window → not_enough_data (change None).
    - `months`: monthly median m/beat for as_of's month and the 11 before,
      oldest first; a month under 4 steady runs keeps its count, value None.
    - `best_efforts`: 90-day best 5k / 10k vs. all-time (Records card rules).
    - `fitness`: the COROS VO₂ max / threshold / running-level step series.

    Runs without avg HR never count toward efficiency. Read-only.
    """
    as_of = as_of or toronto_today()
    runs = activities_svc.unified_activities(db, date_to=as_of)   # whole history: all-time bests need it

    recent_start = as_of - timedelta(days=FORM_RECENT_DAYS - 1)
    baseline_start = recent_start - timedelta(days=FORM_BASELINE_DAYS)
    first_month = date(as_of.year, as_of.month, 1)
    for _ in range(FORM_MONTHS - 1):
        first_month = (first_month - timedelta(days=1)).replace(day=1)
    oldest_needed = min(baseline_start, first_month)

    recent: list[float] = []
    baseline: list[float] = []
    by_month: dict[str, list[float]] = {}
    for r in runs:
        if r.date < oldest_needed:
            continue
        eff = m_per_beat(r)
        if eff is None:
            continue
        if r.date >= recent_start:
            recent.append(eff)
        elif r.date >= baseline_start:
            baseline.append(eff)
        if r.date >= first_month:
            by_month.setdefault(_month_key(r.date), []).append(eff)

    months = []
    m = first_month
    for _ in range(FORM_MONTHS):
        effs = by_month.get(_month_key(m), [])
        value = round(statistics.median(effs), M_PER_BEAT_DECIMALS) if len(effs) >= MIN_MONTH_RUNS else None
        months.append(EfficiencyMonth(month=_month_key(m), steady_runs=len(effs), m_per_beat=value))
        m = (m + timedelta(days=32)).replace(day=1)

    recent_med = statistics.median(recent) if recent else None
    baseline_med = statistics.median(baseline) if baseline else None
    change: Optional[float] = None
    if len(recent) < MIN_STEADY_RUNS or len(baseline) < MIN_STEADY_RUNS:
        verdict = "not_enough_data"
    else:
        change = round((recent_med / baseline_med - 1) * 100, 1)
        if change > IMPROVING_ABOVE_PCT:
            verdict = "improving"
        elif change < SLIPPING_BELOW_PCT:
            verdict = "slipping"
        else:
            verdict = "steady"

    return FormTrend(
        as_of=as_of.isoformat(),
        verdict=verdict,
        change_pct=change,
        recent_m_per_beat=round(recent_med, M_PER_BEAT_DECIMALS) if recent_med is not None else None,
        recent_steady_runs=len(recent),
        baseline_m_per_beat=round(baseline_med, M_PER_BEAT_DECIMALS) if baseline_med is not None else None,
        baseline_steady_runs=len(baseline),
        months=months,
        best_efforts=_rolling_bests(db, runs, as_of),
        fitness=_fitness_line(db, as_of),
    )
