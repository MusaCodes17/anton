"""activities: exclude_from_analysis, exclude_reason, exclude_note

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-10-20

R11.4: per-activity "excluded from analysis" flag with a controlled reason
(app/utils/exclusion_reasons.py) and an optional note. Additive: the boolean is
NOT NULL with a server default of false, so every existing row backfills to
"included" and behavior is unchanged until the runner flags a run. The flag
removes a run from derived analytics only -- never from the mileage ledger or
volume totals (INV-1/INV-2). Downgrade drops the three columns (flags set since
the upgrade are lost; no other data is touched).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("activities") as batch:
        batch.add_column(sa.Column("exclude_from_analysis", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("exclude_reason", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("exclude_note", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("activities") as batch:
        batch.drop_column("exclude_note")
        batch.drop_column("exclude_reason")
        batch.drop_column("exclude_from_analysis")
