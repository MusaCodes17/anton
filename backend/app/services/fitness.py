"""Athlete fitness snapshots (R2.7 T5).

COROS athlete-level metrics (VO2 max, lactate-threshold pace, race predictions)
are stored as append-only `AthleteMetric` rows — one per sync. Anton never
computes these; they arrive from the Claude-Desktop COROS agent (design
decisions C6) via the `record_athlete_metrics` MCP tool. The Training-tab
fitness card reads the newest snapshot; older rows are kept for future trends.
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
    metric should be present; the caller (the confirmation-gated sync agent)
    decides what COROS returned."""
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
