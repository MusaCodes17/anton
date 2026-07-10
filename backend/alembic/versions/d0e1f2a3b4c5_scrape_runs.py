"""add scrape_runs observability table

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-08

R2.5 scrape observability. Persist one row per retailer per full-catalog scrape
attempt (started/finished/status/counts/error) so "is Altitude quietly broken?"
becomes a query instead of log archaeology, and R4.1 (scheduling) / R4.5
(watchdog) have a durable substrate to write into.

Pure schema add — no data moves, nothing pre-exists to reconcile. The table is
deals-domain telemetry (disposable, cascade-deleted with its retailer), so
create_all covers fresh installs; this migration is the source of truth for the
live DB. Reversible: downgrade drops the table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'scrape_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('retailer_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='running', nullable=False),
        sa.Column('trigger', sa.String(length=20), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('shoes_scraped', sa.Integer(), server_default='0', nullable=False),
        sa.Column('products_found', sa.Integer(), server_default='0', nullable=False),
        sa.Column('prices_recorded', sa.Integer(), server_default='0', nullable=False),
        sa.Column('deals_found', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['retailer_id'], ['retailers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_scrape_runs_id'), 'scrape_runs', ['id'], unique=False)
    op.create_index(op.f('ix_scrape_runs_retailer_id'), 'scrape_runs', ['retailer_id'], unique=False)
    op.create_index(op.f('ix_scrape_runs_started_at'), 'scrape_runs', ['started_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_scrape_runs_started_at'), table_name='scrape_runs')
    op.drop_index(op.f('ix_scrape_runs_retailer_id'), table_name='scrape_runs')
    op.drop_index(op.f('ix_scrape_runs_id'), table_name='scrape_runs')
    op.drop_table('scrape_runs')
