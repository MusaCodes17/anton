"""price_records: composite indexes for the watchlist window queries

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-10-10

Perf (watchlist): `services/watchlist.build_watchlist` runs two window-function
queries over price_records (best-ever per shoe; latest per shoe+retailer).
These composite indexes let SQLite read rows already in partition/order
sequence instead of sorting ~28k rows into a temp b-tree. Purely additive;
downgrade drops them and loses nothing.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("price_records") as batch:
        batch.create_index("ix_price_records_shoe_price_id", ["shoe_id", "price", "id"])
        batch.create_index(
            "ix_price_records_shoe_retailer_scraped_id",
            ["shoe_id", "retailer_id", "scraped_at", "id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("price_records") as batch:
        batch.drop_index("ix_price_records_shoe_retailer_scraped_id")
        batch.drop_index("ix_price_records_shoe_price_id")
