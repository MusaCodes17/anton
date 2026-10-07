"""pending_coros_runs + coros_sync_state (COROS direct sync §4, roadmap R5.7)

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2026-10-07

Additive only. `activities.coros_activity_id` already exists (indexed, String)
and is already the dedup key of the sanctioned COROS write path, so — contrary
to the plan's contingency — NO column is added to the runs table.

`pending_coros_runs` is the inbox the poller fills and the runner confirms. It
stores the normalized COROS run (detail prefetched) keyed on COROS `label_id`
(UNIQUE — the poller's exactly-once guarantee). It is not a run record: nothing
here touches activities / shoe_runs / mileage (INV-1, INV-9).
`coros_sync_state` is a single row (id = 1) holding the last-sync summary.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8b9c0d1e2f3a"
down_revision: Union[str, None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pending_coros_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label_id", sa.String(40), nullable=False, unique=True),
        sa.Column("sport_type", sa.Integer(), nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("moving_time_s", sa.Integer(), nullable=False),
        sa.Column("elapsed_time_s", sa.Integer(), nullable=True),
        sa.Column("avg_pace_s_per_km", sa.Integer(), nullable=False),
        sa.Column("avg_hr", sa.Integer(), nullable=True),
        sa.Column("calories", sa.Float(), nullable=True),
        sa.Column("elevation_gain_m", sa.Float(), nullable=True),
        sa.Column("avg_cadence", sa.Float(), nullable=True),
        sa.Column("training_load", sa.Float(), nullable=True),
        sa.Column("training_focus", sa.String(50), nullable=True),
        sa.Column("start_timestamp", sa.Integer(), nullable=False),
        sa.Column("end_timestamp", sa.Integer(), nullable=False),
        sa.Column("suggested_shoe_id", sa.Integer(),
                  sa.ForeignKey("owned_shoes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("suggestion_reason", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pending_coros_runs_status", "pending_coros_runs", ["status"])
    op.create_table(
        "coros_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_trigger", sa.String(20), nullable=True),
        sa.Column("runs_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("coros_sync_state")
    op.drop_index("ix_pending_coros_runs_status", table_name="pending_coros_runs")
    op.drop_table("pending_coros_runs")
