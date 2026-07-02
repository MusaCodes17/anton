"""add_mileage_limit_to_owned_shoes

Revision ID: 6c68ff4148ff
Revises: cf1eccba0a79
Create Date: 2026-07-02

Add mileage_limit (nullable Float) to owned_shoes so users can record the
km at which they plan to retire a shoe. The _format_mileage_bar function in
mcp_server.py now uses this column directly instead of probing via getattr.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '6c68ff4148ff'
down_revision: Union[str, None] = 'cf1eccba0a79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('owned_shoes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mileage_limit', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('owned_shoes', schema=None) as batch_op:
        batch_op.drop_column('mileage_limit')
