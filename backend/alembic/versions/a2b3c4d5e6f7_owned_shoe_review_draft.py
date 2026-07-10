"""Add review_draft to owned_shoes (R3.3 shoe review pipeline).

Revision ID: a2b3c4d5e6f7
Revises:     0b1c2d3e4f5a
Create Date: 2026-07-10

R3.3 — Adds nullable Text column `review_draft` to `owned_shoes` so the
shoe review pipeline can persist the LLM-drafted (and runner-edited) review
alongside the shoe. Purely additive; downgrade drops the column. No data is
moved; E4 ceremony not required.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = '0b1c2d3e4f5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('owned_shoes') as batch_op:
        batch_op.add_column(sa.Column('review_draft', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('owned_shoes') as batch_op:
        batch_op.drop_column('review_draft')
