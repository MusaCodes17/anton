"""activity_splits table, activity_effort_scans.scan_version

Revision ID: b9c0d1e2f3a4
Revises: f5a6b7c8d9e0
Create Date: 2026-10-20

R5.4.3 / R11.6: per-km splits for every scanned run, with average heart rate
(moving-time weighted) and elevation gain/loss, all nullable. Additive: a new table and
one NOT NULL column with a server default of 1, so every existing scan reads as
version 1 and is re-scanned once to gain splits (services/best_efforts
SCAN_VERSION = 2). `attempts` now counts tries for the current scan version, so
upgrade() resets it to 1 on settled (ok/no_stream) rows: earlier rescans (e.g. the
R5.4.1 location backfill) had pushed it to 2, which would leave one failure from
the retry cap. Harmless: failed rows are untouched, and attempts on settled rows
only gates retries, never data. Splits are derived from the FIT/GPX stream and
rebuilt by re-scanning, so downgrade drops the column and the table without losing
anything that cannot be regenerated; it does not restore the old attempts values.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_splits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("split_index", sa.Integer(), nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=False),
        sa.Column("elapsed_s", sa.Integer(), nullable=False),
        sa.Column("moving_s", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("avg_hr", sa.Integer(), nullable=True),
        sa.Column("elev_gain_m", sa.Float(), nullable=True),
        sa.Column("elev_loss_m", sa.Float(), nullable=True),
        sa.UniqueConstraint("activity_id", "split_index", name="uq_split_activity_index"),
    )
    op.create_index("ix_activity_splits_activity_id", "activity_splits", ["activity_id"])
    with op.batch_alter_table("activity_effort_scans") as batch:
        batch.add_column(sa.Column("scan_version", sa.Integer(), nullable=False, server_default="1"))
    # attempts now counts tries for the current scan version; settled rows start at 1
    # so each gets the full retry budget for the splits upgrade.
    op.execute("UPDATE activity_effort_scans SET attempts = 1 WHERE status IN ('ok', 'no_stream')")


def downgrade() -> None:
    with op.batch_alter_table("activity_effort_scans") as batch:
        batch.drop_column("scan_version")
    op.drop_index("ix_activity_splits_activity_id", table_name="activity_splits")
    op.drop_table("activity_splits")
