"""activities: weather at run (weather_temp_c, apparent_temp_c, humidity_pct, wind_speed_m_s)

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-10-10

R5.4.2 (free half): project the weather Strava already recorded -- kept in
``activities.raw_json`` since import -- into typed nullable columns, backfilled
for ``source = 'strava'`` rows via ``weather_from_raw``. Additive and derived
from data kept in the same row, so downgrade simply drops the columns and
loses nothing (re-upgrade re-derives them).
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.utils.strava_weather import weather_from_raw

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("weather_temp_c", "apparent_temp_c", "humidity_pct", "wind_speed_m_s")


def upgrade() -> None:
    with op.batch_alter_table("activities") as batch:
        for name in _COLUMNS:
            batch.add_column(sa.Column(name, sa.Float(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, raw_json FROM activities WHERE source = 'strava' AND raw_json IS NOT NULL")
    ).fetchall()
    update = sa.text(
        "UPDATE activities SET weather_temp_c = :weather_temp_c, apparent_temp_c = :apparent_temp_c, "
        "humidity_pct = :humidity_pct, wind_speed_m_s = :wind_speed_m_s WHERE id = :id"
    )
    for row_id, raw in rows:
        if isinstance(raw, (str, bytes)):
            try:
                raw = json.loads(raw)
            except ValueError:
                continue
        weather = weather_from_raw(raw if isinstance(raw, dict) else None)
        if any(v is not None for v in weather.values()):
            bind.execute(update, {"id": row_id, **weather})


def downgrade() -> None:
    with op.batch_alter_table("activities") as batch:
        for name in reversed(_COLUMNS):
            batch.drop_column(name)
