"""athlete_metrics running_level

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-08

F3 — Add nullable running_level (Float) to athlete_metrics so the sync_fitness
agent can persist COROS fitness-assessment running level alongside VO2 max and
threshold pace. Pure additive column; downgrade drops it. E4: live DB backed up
to shoe_deals.db.bak-running-level before applying.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('athlete_metrics') as batch_op:
        batch_op.add_column(sa.Column('running_level', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('athlete_metrics') as batch_op:
        batch_op.drop_column('running_level')
