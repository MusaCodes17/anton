"""canonical activities table (§3 Phase-5)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-04

Collapse the two run stores into one canonical `activities` table and demote
`shoe_runs` to a pure attribution row:

- Create `activities` (superset of the old `strava_activities` columns + a
  `source` discriminator + `coros_activity_id`).
- Migrate every `strava_activities` row in (source='strava'), then walk the
  old data-bearing `shoe_runs`: a *linked* run (strava_activity_id set) becomes
  attribution for the already-migrated strava activity (stamping its
  coros_activity_id when present); an *unlinked* run mints a fresh activity.
- Rebuild `shoe_runs` as {id, activity_id, owned_shoe_id, created_at}.
- Drop `strava_activities`.

Reversible: downgrade recreates `strava_activities` from source='strava'
activities and reconstitutes the old data-bearing `shoe_runs` by joining
attribution -> activity.

Self-contained (Core + inline pace helpers) so it doesn't couple to app code
that may drift after this revision.
"""
from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── inline pace helpers (mirror app.services.rotation) ──────────────────────
def _pace_to_seconds(pace: Optional[str]) -> Optional[int]:
    if not pace:
        return None
    try:
        mins, secs = pace.split('/')[0].strip().split(':')
        return int(mins) * 60 + int(secs)
    except (ValueError, AttributeError):
        return None


def _seconds_to_pace(seconds: Optional[int]) -> Optional[str]:
    if seconds is None:
        return None
    total = round(seconds)
    mins, secs = divmod(total, 60)
    return f"{mins}:{secs:02d}/km"


# ── column definitions, kept in one place for up/down symmetry ──────────────
_ACTIVITIES_COLS = (
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
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
    sa.Column('strava_activity_id', sa.BigInteger(), nullable=True),
    sa.Column('coros_activity_id', sa.String(length=100), nullable=True),
    sa.Column('gear_name', sa.String(length=200), nullable=True),
    sa.Column('fit_filename', sa.String(length=300), nullable=True),
    sa.Column('grade_adjusted_distance_m', sa.Float(), nullable=True),
    sa.Column('raw_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
)

_STRAVA_COLS = (
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
)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Canonical activities table.
    op.create_table('activities', *_ACTIVITIES_COLS, sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_activities_id'), 'activities', ['id'])
    op.create_index(op.f('ix_activities_source'), 'activities', ['source'])
    op.create_index(op.f('ix_activities_activity_type'), 'activities', ['activity_type'])
    op.create_index(op.f('ix_activities_run_date'), 'activities', ['run_date'])
    op.create_index(op.f('ix_activities_strava_activity_id'), 'activities', ['strava_activity_id'], unique=True)
    op.create_index(op.f('ix_activities_coros_activity_id'), 'activities', ['coros_activity_id'])
    op.create_index(op.f('ix_activities_gear_name'), 'activities', ['gear_name'])

    # 2. Every strava_activities row -> activities (source='strava'), preserving
    #    strava_activity_id so we can look attributions back up by it.
    conn.execute(sa.text(
        "INSERT INTO activities (source, activity_type, name, description, started_at_utc, "
        "started_at_local, run_date, distance_km, moving_time_s, elapsed_time_s, avg_hr, max_hr, "
        "avg_pace_s_per_km, elevation_gain_m, avg_cadence, calories, strava_activity_id, gear_name, "
        "fit_filename, grade_adjusted_distance_m, raw_json, created_at) "
        "SELECT 'strava', activity_type, name, description, started_at_utc, started_at_local, "
        "run_date, distance_km, moving_time_s, elapsed_time_s, avg_hr, max_hr, avg_pace_s_per_km, "
        "elevation_gain_m, avg_cadence, calories, strava_activity_id, gear_name, fit_filename, "
        "grade_adjusted_distance_m, raw_json, created_at FROM strava_activities"
    ))

    # 3. Walk the old data-bearing shoe_runs, building attribution rows.
    old_runs = conn.execute(sa.text(
        "SELECT id, owned_shoe_id, distance_km, run_date, source, coros_activity_id, "
        "strava_activity_id, avg_pace, avg_hr, notes, created_at FROM shoe_runs"
    )).fetchall()

    attributions = []  # (activity_id, owned_shoe_id, created_at)
    for r in old_runs:
        if r.strava_activity_id is not None:
            # Linked: attribute the already-migrated strava activity.
            act = conn.execute(
                sa.text("SELECT id FROM activities WHERE strava_activity_id = :sid"),
                {"sid": r.strava_activity_id},
            ).fetchone()
            if act is None:
                continue  # orphaned link (shouldn't happen); skip defensively
            activity_id = act.id
            if r.coros_activity_id:
                conn.execute(
                    sa.text("UPDATE activities SET coros_activity_id = :c WHERE id = :i"),
                    {"c": r.coros_activity_id, "i": activity_id},
                )
        else:
            # Unlinked post-export run: mint a fresh activity from the run.
            res = conn.execute(
                sa.text(
                    "INSERT INTO activities (source, activity_type, run_date, distance_km, "
                    "avg_pace_s_per_km, avg_hr, coros_activity_id, description, created_at) "
                    "VALUES (:source, 'Run', :run_date, :distance_km, :pace, :hr, :coros, :desc, :created)"
                ),
                {
                    "source": r.source or "manual",
                    "run_date": r.run_date,
                    "distance_km": r.distance_km,
                    "pace": _pace_to_seconds(r.avg_pace),
                    "hr": r.avg_hr,
                    "coros": r.coros_activity_id,
                    "desc": r.notes,
                    "created": r.created_at,
                },
            )
            activity_id = res.lastrowid
        attributions.append((activity_id, r.owned_shoe_id, r.created_at))

    # 4. Rebuild shoe_runs as attribution-only.
    op.create_table(
        'shoe_runs_new',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('activity_id', sa.Integer(), nullable=False),
        sa.Column('owned_shoe_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['activity_id'], ['activities.id']),
        sa.ForeignKeyConstraint(['owned_shoe_id'], ['owned_shoes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for activity_id, owned_shoe_id, created_at in attributions:
        conn.execute(
            sa.text(
                "INSERT INTO shoe_runs_new (activity_id, owned_shoe_id, created_at) "
                "VALUES (:a, :s, :c)"
            ),
            {"a": activity_id, "s": owned_shoe_id, "c": created_at},
        )

    op.drop_table('shoe_runs')
    op.rename_table('shoe_runs_new', 'shoe_runs')
    op.create_index(op.f('ix_shoe_runs_id'), 'shoe_runs', ['id'])
    op.create_index(op.f('ix_shoe_runs_activity_id'), 'shoe_runs', ['activity_id'], unique=True)
    op.create_index(op.f('ix_shoe_runs_owned_shoe_id'), 'shoe_runs', ['owned_shoe_id'])

    # 5. Drop the now-redundant strava_activities archive (data lives in activities).
    op.drop_table('strava_activities')


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Recreate strava_activities and refill from source='strava' activities.
    op.create_table('strava_activities', *_STRAVA_COLS, sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_strava_activities_id'), 'strava_activities', ['id'])
    op.create_index(op.f('ix_strava_activities_strava_activity_id'), 'strava_activities', ['strava_activity_id'], unique=True)
    op.create_index(op.f('ix_strava_activities_activity_type'), 'strava_activities', ['activity_type'])
    op.create_index(op.f('ix_strava_activities_run_date'), 'strava_activities', ['run_date'])
    op.create_index(op.f('ix_strava_activities_gear_name'), 'strava_activities', ['gear_name'])
    conn.execute(sa.text(
        "INSERT INTO strava_activities (strava_activity_id, activity_type, name, description, "
        "started_at_utc, started_at_local, run_date, distance_km, moving_time_s, elapsed_time_s, "
        "avg_hr, max_hr, avg_pace_s_per_km, elevation_gain_m, avg_cadence, calories, gear_name, "
        "fit_filename, grade_adjusted_distance_m, raw_json, created_at) "
        "SELECT strava_activity_id, activity_type, name, description, started_at_utc, started_at_local, "
        "run_date, distance_km, moving_time_s, elapsed_time_s, avg_hr, max_hr, avg_pace_s_per_km, "
        "elevation_gain_m, avg_cadence, calories, gear_name, fit_filename, grade_adjusted_distance_m, "
        "raw_json, created_at FROM activities WHERE source = 'strava'"
    ))

    # 2. Reconstitute data-bearing shoe_runs by joining attribution -> activity.
    rows = conn.execute(sa.text(
        "SELECT sr.owned_shoe_id, sr.created_at, a.distance_km, a.run_date, a.source, "
        "a.coros_activity_id, a.strava_activity_id, a.avg_pace_s_per_km, a.avg_hr, a.description "
        "FROM shoe_runs sr JOIN activities a ON a.id = sr.activity_id"
    )).fetchall()

    op.create_table(
        'shoe_runs_old',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owned_shoe_id', sa.Integer(), nullable=False),
        sa.Column('distance_km', sa.Float(), nullable=False),
        sa.Column('run_date', sa.Date(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False, server_default='manual'),
        sa.Column('coros_activity_id', sa.String(length=100), nullable=True),
        sa.Column('strava_activity_id', sa.BigInteger(), nullable=True),
        sa.Column('avg_pace', sa.String(length=20), nullable=True),
        sa.Column('avg_hr', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['owned_shoe_id'], ['owned_shoes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('strava_activity_id', name='uq_shoe_runs_strava_activity_id'),
    )
    for r in rows:
        conn.execute(
            sa.text(
                "INSERT INTO shoe_runs_old (owned_shoe_id, distance_km, run_date, source, "
                "coros_activity_id, strava_activity_id, avg_pace, avg_hr, notes, created_at) "
                "VALUES (:shoe, :dist, :date, :source, :coros, :strava, :pace, :hr, :notes, :created)"
            ),
            {
                "shoe": r.owned_shoe_id,
                "dist": r.distance_km,
                "date": r.run_date,
                "source": r.source,
                "coros": r.coros_activity_id,
                "strava": r.strava_activity_id,
                "pace": _seconds_to_pace(r.avg_pace_s_per_km),
                "hr": r.avg_hr,
                "notes": r.description,
                "created": r.created_at,
            },
        )

    op.drop_table('shoe_runs')
    op.rename_table('shoe_runs_old', 'shoe_runs')
    op.create_index(op.f('ix_shoe_runs_id'), 'shoe_runs', ['id'])
    op.create_index(op.f('ix_shoe_runs_owned_shoe_id'), 'shoe_runs', ['owned_shoe_id'])
    op.create_index(op.f('ix_shoe_runs_coros_activity_id'), 'shoe_runs', ['coros_activity_id'])

    # 3. Drop the canonical table.
    op.drop_index(op.f('ix_activities_gear_name'), table_name='activities')
    op.drop_index(op.f('ix_activities_coros_activity_id'), table_name='activities')
    op.drop_index(op.f('ix_activities_strava_activity_id'), table_name='activities')
    op.drop_index(op.f('ix_activities_run_date'), table_name='activities')
    op.drop_index(op.f('ix_activities_activity_type'), table_name='activities')
    op.drop_index(op.f('ix_activities_source'), table_name='activities')
    op.drop_index(op.f('ix_activities_id'), table_name='activities')
    op.drop_table('activities')
