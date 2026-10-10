"""activities + pending_coros_runs: start location (start_lat, start_lng, location_label)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-10

R5.4.1: optional, nullable start point of a run. Coordinates are stored
already rounded (app.utils.location.COORD_DECIMALS) -- never a track. Adding
nullable columns moves no data, so downgrade simply drops them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("activities", "pending_coros_runs")


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("start_lat", sa.Float(), nullable=True))
            batch.add_column(sa.Column("start_lng", sa.Float(), nullable=True))
            batch.add_column(sa.Column("location_label", sa.String(length=200), nullable=True))


def downgrade() -> None:
    for table in reversed(_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("location_label")
            batch.drop_column("start_lng")
            batch.drop_column("start_lat")
