"""msrp_drives_deals — make target_price nullable on shoes and deals

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-06

Deal qualification and savings % now measure against a shoe's MSRP, not its
target_price (see DealStore.upsert_deal / ScrapeOrchestrator). target_price is
demoted to an optional personal threshold, so its NOT NULL constraint is
relaxed on both shoes.target_price and deals.target_price.

Structural-only: no rows are moved or recomputed here. Existing deal
savings_amount/savings_percent were computed against target_price and will be
recomputed against MSRP on the next scrape (or by the one-off recompute the
changelog documents). Reversible: downgrade restores NOT NULL, which requires
every row to have a non-null target_price at that time.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('shoes', schema=None) as batch_op:
        batch_op.alter_column('target_price', existing_type=sa.Float(), nullable=True)
    with op.batch_alter_table('deals', schema=None) as batch_op:
        batch_op.alter_column('target_price', existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # Requires no null target_price rows to exist (they'd violate NOT NULL).
    with op.batch_alter_table('deals', schema=None) as batch_op:
        batch_op.alter_column('target_price', existing_type=sa.Float(), nullable=False)
    with op.batch_alter_table('shoes', schema=None) as batch_op:
        batch_op.alter_column('target_price', existing_type=sa.Float(), nullable=False)
