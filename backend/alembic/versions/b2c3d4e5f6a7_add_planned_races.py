"""add_planned_races

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-04

Create the planned_races table (P3.4) — races the user is training toward,
each optionally linked to an owned shoe. Derived fields (days/weeks
remaining, target pace) are computed at the API boundary, not stored.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'planned_races',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('race_date', sa.Date(), nullable=False),
        sa.Column('distance_km', sa.Float(), nullable=True),
        sa.Column('target_time_s', sa.Integer(), nullable=True),
        sa.Column('location', sa.String(length=200), nullable=True),
        sa.Column('planned_shoe_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='planned', nullable=False),
        sa.Column('result_time_s', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['planned_shoe_id'], ['owned_shoes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_planned_races_id'), 'planned_races', ['id'], unique=False)
    op.create_index(op.f('ix_planned_races_race_date'), 'planned_races', ['race_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_planned_races_race_date'), table_name='planned_races')
    op.drop_index(op.f('ix_planned_races_id'), table_name='planned_races')
    op.drop_table('planned_races')
