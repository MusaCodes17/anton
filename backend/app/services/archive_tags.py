"""
Reviewed backfill of `activity_tag` for the Strava archive (R5.5.3).

Strava's bulk export carries no workout-type field, so run *names* are the only
signal. This module proposes tags for untagged archive runs using the same
T8 name rules COROS sync uses (`suggest_tag_from_name`) and shows what the
change would do *before* anything is written: per-tag counts, which race PBs
would appear or change (Race/Parkrun tags feed `personal_bests`), and how many
runs would leave the form trend's steady-run pool (untagged counts as steady).

Two steps, deliberately separate (C9 — the human is the tiebreaker):
  - `plan_archive_tags` is read-only (the PB what-if runs inside a SAVEPOINT
    that is always rolled back).
  - `apply_archive_tags` is the confirmation step and only ever follows a plan
    the runner has reviewed.
Runner-set tags always win: an already-tagged run is never a candidate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Activity
from app.services.strava_stats import PersonalBest, personal_bests
from app.services.training_trends import STEADY_TAGS
from app.utils.activity_tags import suggest_tag_from_name


@dataclass
class TagSuggestion:
    activity_id: int
    run_date: Optional[object]  # datetime.date | None
    name: Optional[str]
    distance_km: Optional[float]
    tag: str


@dataclass
class TagPlan:
    suggestions: list[TagSuggestion] = field(default_factory=list)
    by_tag: dict[str, int] = field(default_factory=dict)
    untouched: int = 0                       # untagged archive runs no rule matched
    race_pbs_added: list[str] = field(default_factory=list)
    race_pbs_changed: list[str] = field(default_factory=list)
    steady_runs_removed: int = 0             # suggestions whose tag leaves STEADY_TAGS


def _fmt_time(total_s: int) -> str:
    h, rem = divmod(int(total_s), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fmt_pb(pb: Optional[PersonalBest]) -> str:
    if pb is None:
        return "none"
    return f"{_fmt_time(pb.total_time_s)} ({pb.run_date}, '{pb.name}')"


def plan_archive_tags(db: Session) -> TagPlan:
    """Propose tags for untagged Strava-archive runs. Writes nothing: the PB
    what-if applies the tags inside a SAVEPOINT and always rolls it back (the
    caller's session is left with the original tags). Never proposes a tag for
    a run that already has one."""
    candidates = (
        db.query(Activity)
        .filter(Activity.source == "strava", Activity.activity_type == "Run",
                Activity.activity_tag.is_(None))
        .order_by(Activity.run_date, Activity.id)
        .all()
    )
    plan = TagPlan()
    chosen: list[tuple[Activity, str]] = []
    for a in candidates:
        tag = suggest_tag_from_name(a.name)
        if tag is None:
            plan.untouched += 1
            continue
        chosen.append((a, tag))
        plan.suggestions.append(TagSuggestion(a.id, a.run_date, a.name, a.distance_km, tag))
        plan.by_tag[tag] = plan.by_tag.get(tag, 0) + 1
        if tag not in STEADY_TAGS:
            plan.steady_runs_removed += 1

    if chosen:
        before = {pb.band: pb for pb in personal_bests(db).race_pbs}
        savepoint = db.begin_nested()
        try:
            for a, tag in chosen:
                a.activity_tag = tag
            db.flush()
            after = {pb.band: pb for pb in personal_bests(db).race_pbs}
        finally:
            savepoint.rollback()
            for a, _ in chosen:   # belt and braces: never leave a planned tag in the session
                db.refresh(a)
        for band, pb in after.items():
            old = before.get(band)
            if old is None:
                plan.race_pbs_added.append(f"{band}: none → {_fmt_pb(pb)}")
            elif old.activity_id != pb.activity_id or old.total_time_s != pb.total_time_s:
                plan.race_pbs_changed.append(f"{band}: {_fmt_pb(old)} → {_fmt_pb(pb)}")
    return plan


def apply_archive_tags(db: Session, plan: TagPlan) -> int:
    """Write the plan's tags — the confirmation step (C9). Only call this with
    a plan the runner has reviewed. Sets exactly the planned suggestions whose
    activity is still untagged (a tag the runner set since the plan wins).
    Commits once; returns the number of runs tagged."""
    ids = [s.activity_id for s in plan.suggestions]
    if not ids:
        return 0
    rows = {a.id: a for a in db.query(Activity).filter(Activity.id.in_(ids)).all()}
    n = 0
    for s in plan.suggestions:
        a = rows.get(s.activity_id)
        if a is not None and a.activity_tag is None:
            a.activity_tag = s.tag
            n += 1
    db.commit()
    return n
