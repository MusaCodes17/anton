"""Athlete fitness snapshots (R2.7 T5; automatic since R8.4.1).

COROS athlete-level metrics (VO2 max, running level, lactate-threshold pace,
race predictions) are stored as append-only `AthleteMetric` rows. Anton never
computes these. Two paths write them:

- **Automatic (R8.4.1, design decisions C13):** the COROS poller reads the
  fitness overview during its sync and calls `record_if_changed`, so a row is a
  real change, not a repeat. No confirmation: a snapshot is a reading COROS
  computed, not a run, so the run gate (INV-8) doesn't apply.
- **Manual:** the `record_athlete_metrics` MCP tool (`sync_fitness` prompt).

The Training-tab fitness card reads the newest snapshot; the rows are the
history R8.4.3 charts.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import AthleteMetric


def record_snapshot(
    db: Session,
    *,
    vo2max: Optional[float] = None,
    threshold_pace_s_per_km: Optional[int] = None,
    race_predictions: Optional[dict] = None,
    running_level: Optional[float] = None,
) -> AthleteMetric:
    """Append a new fitness snapshot (server-stamps `captured_at`). At least one
    metric should be present; the caller decides what COROS returned. Commits."""
    snap = AthleteMetric(
        vo2max=vo2max,
        threshold_pace_s_per_km=threshold_pace_s_per_km,
        race_predictions=race_predictions,
        running_level=running_level,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def latest(db: Session) -> Optional[AthleteMetric]:
    """The most recent snapshot by `captured_at`, or None if none recorded."""
    return (
        db.query(AthleteMetric)
        .order_by(AthleteMetric.captured_at.desc(), AthleteMetric.id.desc())
        .first()
    )


def _values(snap: AthleteMetric) -> tuple:
    return (snap.vo2max, snap.running_level, snap.threshold_pace_s_per_km, snap.race_predictions or None)


def record_if_changed(
    db: Session,
    *,
    vo2max: Optional[float] = None,
    threshold_pace_s_per_km: Optional[int] = None,
    race_predictions: Optional[dict] = None,
    running_level: Optional[float] = None,
) -> Optional[AthleteMetric]:
    """Append a snapshot only when it differs from the latest one (R8.4.1), so
    each row in the history is a real change. Returns the new row, or None when
    nothing changed or every metric is absent (COROS had nothing to report).
    Commits when it writes.

    A metric COROS stopped reporting counts as a change and is stored as None:
    the snapshot records what COROS said, nothing carried forward.
    """
    new = (vo2max, running_level, threshold_pace_s_per_km, race_predictions or None)
    if all(v is None for v in new):
        return None
    prev = latest(db)
    if prev is not None and _values(prev) == new:
        return None
    return record_snapshot(
        db, vo2max=vo2max, threshold_pace_s_per_km=threshold_pace_s_per_km,
        race_predictions=race_predictions, running_level=running_level,
    )
