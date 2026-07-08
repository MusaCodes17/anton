"""athlete_metrics

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-07

R2.7 T5 — a new append-only table of periodic COROS athlete-level fitness
snapshots (VO2 max, lactate-threshold pace, race predictions). Purely additive
(new table); downgrade drops it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'athlete_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vo2max', sa.Float(), nullable=True),
        sa.Column('threshold_pace_s_per_km', sa.Integer(), nullable=True),
        sa.Column('race_predictions', sa.JSON(), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_athlete_metrics_id', 'athlete_metrics', ['id'])
    op.create_index('ix_athlete_metrics_captured_at', 'athlete_metrics', ['captured_at'])


def downgrade() -> None:
    op.drop_index('ix_athlete_metrics_captured_at', table_name='athlete_metrics')
    op.drop_index('ix_athlete_metrics_id', table_name='athlete_metrics')
    op.drop_table('athlete_metrics')
