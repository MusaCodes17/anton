"""normalize legacy owned_shoes.shoe_type to the R2.4 vocabulary

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-08

R2.4 promotes `shoe_type` to a backend-owned controlled vocabulary and validates
it on write. Nine legacy `owned_shoes` rows carried free-text values that predate
the vocabulary (`Daily Trainer`, `Race Shoe`, `Tempo shoe`/`Tempo Shoe`,
`Recovery Shoe`) — off-vocabulary, so the cross-domain replacement-deals join
silently found nothing, and (post-R2.4) editing them through the form would 422.

This normalizes those exact rows to the canonical vocabulary. It is a **by-id**
remap guarded on the current value, so it is idempotent and a safe no-op on any
DB that doesn't hold these specific legacy rows (a fresh install, or a re-run).
The two "Race Shoe" pairs split per shoe (confirmed with the runner 2026-07-08):
the Adios Pro 3 is a marathon super-shoe (`long_distance_racer`); the Streakfly is
a lightweight 5K/10K racer (`short_distance_racer`).

E4 discipline: reversible (the downgrade restores each row's original free-text by
id), a named live-DB backup was taken before applying, and pre/post counts were
reconciled (see changelog 2026-07-08). Data-only — no schema change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (owned_shoes.id, legacy free-text value, canonical vocabulary value)
_REMAP: tuple[tuple[int, str, str], ...] = (
    (3,  'Daily Trainer', 'daily_trainer'),
    (18, 'Daily Trainer', 'daily_trainer'),
    (19, 'Daily Trainer', 'daily_trainer'),
    (21, 'Daily Trainer', 'daily_trainer'),
    (10, 'Race Shoe',     'long_distance_racer'),   # Adidas Adios Pro 3
    (15, 'Race Shoe',     'short_distance_racer'),  # Nike Streakfly
    (22, 'Recovery Shoe', 'recovery'),
    (17, 'Tempo Shoe',    'tempo'),
    (4,  'Tempo shoe',    'tempo'),
)

_STMT = sa.text(
    "UPDATE owned_shoes SET shoe_type = :new "
    "WHERE id = :id AND shoe_type = :old"
)


def _apply(pairs) -> None:
    bind = op.get_bind()
    for row_id, frm, to in pairs:
        bind.execute(_STMT, {"id": row_id, "old": frm, "new": to})


def upgrade() -> None:
    _apply((row_id, old, new) for row_id, old, new in _REMAP)


def downgrade() -> None:
    # Restore the exact original free-text values, guarded so we only revert rows
    # we set (never a legitimately-canonical row that happened to match).
    _apply((row_id, new, old) for row_id, old, new in _REMAP)
