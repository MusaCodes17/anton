"""add_strava_import_tables

Revision ID: a1b2c3d4e5f6
Revises: 6c68ff4148ff
Create Date: 2026-07-03

Strava historical import (§1 of the import plan):
- new table strava_activities (canonical import of every activity)
- new table strava_gear_mappings (gear string -> owned shoe, nullable)
- shoe_runs gains strava_activity_id (BigInteger, unique, nullable) — the
  idempotency guard linking a run to at most one Strava activity.
- shoe_runs.source already existed as a column but without a server_default;
  add one ('manual') so raw INSERTs are safe, and backfill existing rows:
  any run carrying a coros_activity_id is a COROS import -> 'coros'.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '6c68ff4148ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'strava_activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('strava_activity_id', sa.BigInteger(), nullable=False),
        sa.Column('activity_type', sa.String(length=50), nullable=True),
        sa.Column('name', sa.String(length=500), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('started_at_utc', sa.DateTime(), nullable=True),
        sa.Column('started_at_local', sa.DateTime(), nullable=True),
        sa.Column('run_date', sa.Date(), nullable=True),
        sa.Column('distance_km', sa.Float(), nullable=True),
        sa.Column('moving_time_s', sa.Integer(), nullable=True),
        sa.Column('elapsed_time_s', sa.Integer(), nullable=True),
        sa.Column('avg_hr', sa.Integer(), nullable=True),
        sa.Column('max_hr', sa.Integer(), nullable=True),
        sa.Column('avg_pace_s_per_km', sa.Integer(), nullable=True),
        sa.Column('elevation_gain_m', sa.Float(), nullable=True),
        sa.Column('avg_cadence', sa.Float(), nullable=True),
        sa.Column('calories', sa.Float(), nullable=True),
        sa.Column('gear_name', sa.String(length=200), nullable=True),
        sa.Column('fit_filename', sa.String(length=300), nullable=True),
        sa.Column('grade_adjusted_distance_m', sa.Float(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_strava_activities_id'), 'strava_activities', ['id'], unique=False)
    op.create_index(op.f('ix_strava_activities_strava_activity_id'), 'strava_activities', ['strava_activity_id'], unique=True)
    op.create_index(op.f('ix_strava_activities_activity_type'), 'strava_activities', ['activity_type'], unique=False)
    op.create_index(op.f('ix_strava_activities_run_date'), 'strava_activities', ['run_date'], unique=False)
    op.create_index(op.f('ix_strava_activities_gear_name'), 'strava_activities', ['gear_name'], unique=False)

    op.create_table(
        'strava_gear_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gear_name', sa.String(length=200), nullable=False),
        sa.Column('owned_shoe_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['owned_shoe_id'], ['owned_shoes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('gear_name'),
    )
    op.create_index(op.f('ix_strava_gear_mappings_id'), 'strava_gear_mappings', ['id'], unique=False)

    # shoe_runs: add strava_activity_id + a server_default for source, then backfill.
    with op.batch_alter_table('shoe_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('strava_activity_id', sa.BigInteger(), nullable=True))
        batch_op.alter_column(
            'source',
            existing_type=sa.String(length=20),
            nullable=False,
            server_default='manual',
        )
        batch_op.create_unique_constraint('uq_shoe_runs_strava_activity_id', ['strava_activity_id'])

    # Backfill source for existing COROS-imported rows (identifiable by the
    # coros_activity_id they carry). Everything else stays 'manual'.
    op.execute(
        "UPDATE shoe_runs SET source = 'coros' "
        "WHERE coros_activity_id IS NOT NULL AND coros_activity_id != ''"
    )


def downgrade() -> None:
    with op.batch_alter_table('shoe_runs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_shoe_runs_strava_activity_id', type_='unique')
        batch_op.alter_column(
            'source',
            existing_type=sa.String(length=20),
            nullable=False,
            server_default=None,
        )
        batch_op.drop_column('strava_activity_id')

    op.drop_index(op.f('ix_strava_gear_mappings_id'), table_name='strava_gear_mappings')
    op.drop_table('strava_gear_mappings')

    op.drop_index(op.f('ix_strava_activities_gear_name'), table_name='strava_activities')
    op.drop_index(op.f('ix_strava_activities_run_date'), table_name='strava_activities')
    op.drop_index(op.f('ix_strava_activities_activity_type'), table_name='strava_activities')
    op.drop_index(op.f('ix_strava_activities_strava_activity_id'), table_name='strava_activities')
    op.drop_index(op.f('ix_strava_activities_id'), table_name='strava_activities')
    op.drop_table('strava_activities')
