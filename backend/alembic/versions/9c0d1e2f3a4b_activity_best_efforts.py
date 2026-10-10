"""activity_best_efforts + activity_effort_scans (R8.2 best efforts)

Revision ID: 9c0d1e2f3a4b
Revises: 8b9c0d1e2f3a
Create Date: 2026-10-09

Additive only: two new tables, nothing existing changes, no data moves (the
backfill script fills them afterwards and can be re-run). Both are derived
from activity files and cascade-delete with their activity. See
docs/design_decisions.md B19.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9c0d1e2f3a4b"
down_revision: Union[str, None] = "8b9c0d1e2f3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_best_efforts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(),
                  sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("distance_label", sa.String(10), nullable=False),
        sa.Column("elapsed_s", sa.Integer(), nullable=False),
        sa.Column("start_offset_m", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.UniqueConstraint("activity_id", "distance_label", name="uq_best_effort_activity_distance"),
    )
    op.create_index("ix_activity_best_efforts_activity_id", "activity_best_efforts", ["activity_id"])
    op.create_index("ix_activity_best_efforts_distance_label", "activity_best_efforts", ["distance_label"])
    op.create_table(
        "activity_effort_scans",
        sa.Column("activity_id", sa.Integer(),
                  sa.ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source", sa.String(10), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("activity_effort_scans")
    op.drop_index("ix_activity_best_efforts_distance_label", table_name="activity_best_efforts")
    op.drop_index("ix_activity_best_efforts_activity_id", table_name="activity_best_efforts")
    op.drop_table("activity_best_efforts")
