"""drop deals.expires_at (never written)

Revision ID: ad1e2f3a4b5c
Revises: 9c0d1e2f3a4b
Create Date: 2026-10-10

`deals.expires_at` was a placeholder from the original schema: no scraper,
service or client ever set or read it (645 deals on 2026-10-10, 0 non-null).
Deals end by `is_active` + retirement (INV-6), not by an expiry. Dropping a
column that holds no data moves nothing; downgrade re-adds it empty.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ad1e2f3a4b5c"
down_revision: Union[str, None] = "9c0d1e2f3a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("deals") as batch:
        batch.drop_column("expires_at")


def downgrade() -> None:
    with op.batch_alter_table("deals") as batch:
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
