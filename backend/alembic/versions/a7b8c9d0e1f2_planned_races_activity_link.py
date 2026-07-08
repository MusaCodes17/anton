"""planned_races.activity_id link

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-08

R2.7 T7 — add a nullable `activity_id` FK from `planned_races` to `activities`,
linking a completed race to the canonical run it was (set by the T6
promote-to-race flow). Purely additive nullable column — existing planned rows
stay unlinked, so the downgrade simply drops it (E4 reversibility). No data
movement.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('planned_races', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_planned_races_activity_id', 'activities', ['activity_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('planned_races', schema=None) as batch_op:
        batch_op.drop_constraint('fk_planned_races_activity_id', type_='foreignkey')
        batch_op.drop_column('activity_id')
