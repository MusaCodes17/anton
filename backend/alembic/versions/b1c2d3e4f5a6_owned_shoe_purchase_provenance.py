"""owned_shoes: purchase provenance (purchase_retailer, purchase_url)

Revision ID: b1c2d3e4f5a6
Revises: ad1e2f3a4b5c
Create Date: 2026-10-10

R5.3 step 1: optional, nullable record of where an owned shoe was bought.
Both columns are recorded strings, deliberately NOT foreign keys to
deals/retailers — wanting a shoe (watchlist/deals) and owning it are
independent facts (design decision B1). Adding nullable columns moves no
data, so downgrade simply drops them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "ad1e2f3a4b5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("owned_shoes") as batch:
        batch.add_column(sa.Column("purchase_retailer", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("purchase_url", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("owned_shoes") as batch:
        batch.drop_column("purchase_url")
        batch.drop_column("purchase_retailer")
