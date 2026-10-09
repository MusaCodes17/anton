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
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.models import PlannedRace
from app.services import activities as activities_svc

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
