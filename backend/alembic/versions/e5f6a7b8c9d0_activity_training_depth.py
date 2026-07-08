"""activity_training_depth

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-07

R2.7 T1 — add four nullable training-depth columns to `activities`:
  training_load   (Float)       — COROS training-load score, null if unavailable
  training_focus  (String(50))  — coaching label, e.g. "Aerobic base"
  activity_tag    (String(30))  — controlled vocabulary (app/utils/activity_tags.py),
                                  indexed because the PB query (T3) filters on it
  best_km_pace_s  (Integer)     — best consecutive-km pace within the run (s/km)

Purely additive nullable columns — existing rows stay untagged/unscored, so the
downgrade simply drops them (E4 reversibility). No data movement.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('training_load', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('training_focus', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('activity_tag', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('best_km_pace_s', sa.Integer(), nullable=True))
        batch_op.create_index('ix_activities_activity_tag', ['activity_tag'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.drop_index('ix_activities_activity_tag')
        batch_op.drop_column('best_km_pace_s')
        batch_op.drop_column('activity_tag')
        batch_op.drop_column('training_focus')
        batch_op.drop_column('training_load')
