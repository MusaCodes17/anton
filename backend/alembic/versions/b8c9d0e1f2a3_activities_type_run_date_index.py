"""activities (activity_type, run_date) composite index

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-08

R2.3 — add a composite index `ix_activities_type_run_date` on
`activities(activity_type, run_date)`. Every `unified_activities` read now
filters `activity_type == "Run"` and ranges/orders on `run_date`; this index
serves that leading-column filter plus the newest-first order so the SQL read
path is index-served as the run history grows. Pure schema addition — no data
movement — so the downgrade simply drops the index (E4 reversibility).
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_activities_type_run_date', 'activities',
        ['activity_type', 'run_date'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_activities_type_run_date', table_name='activities')
