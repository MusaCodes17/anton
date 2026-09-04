"""backfill NULL owned_shoes.mileage_limit with per-shoe_type defaults

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-09-04

#8: every one of the 24 owned shoes carried mileage_limit = NULL, so
rotation.retirement_pipeline (which excludes NULL-limit shoes — there's no limit
to be a fraction of) had *nothing* to surface, and the Home shoe-health alert
has never fired. This backfills a sensible default per shoe_type so worn shoes
start showing up in the pipeline; the runner can override any value afterward
via PUT /owned-shoes/{id}.

The map is a product rule (runner-approved 2026-09-04, documented in
docs/domain_model.md). Its runtime home is app/utils/shoe_types.py
(`DEFAULT_MILEAGE_LIMITS` / `default_mileage_limit`), applied on owned-shoe
CREATE. This migration carries a FROZEN copy of that map: Alembic revisions are
immutable historical records and must not import app code whose meaning can
drift. Values here and in shoe_types.py agree as of this revision.

Since R2.4 (migration c9d0e1f2a3b4) every owned_shoes.shoe_type is a member of
the canonical vocabulary, so the map covers the actual values; the upgrade first
reads DISTINCT shoe_type over the NULL-limit rows and applies the frozen map
with a 600 km fallback for a NULL or unmapped type, guaranteeing every affected
row gets a limit.

E4 discipline: reversible (downgrade NULLs out only rows whose limit still
equals the default this set, guarded by shoe_type + value — mirrors the
c9d0e1f2a3b4 normalize migration), a named live-DB backup is taken before
applying (shoe_deals.db.bak-mileage-defaults), and pre/post counts of NULL vs
non-NULL mileage_limit are reconciled (see the changelog entry). Data-only — no
schema change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "2b3c4d5e6f7a"
down_revision: Union[str, None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# FROZEN copy of app.utils.shoe_types.DEFAULT_MILEAGE_LIMITS as of this revision.
_DEFAULTS: dict[str, float] = {
    "long_distance_racer": 450.0,
    "short_distance_racer": 450.0,
    "tempo": 500.0,
    "intervals": 500.0,
    "long_run": 700.0,
    "daily_trainer": 700.0,
    "recovery": 700.0,
    "trail": 600.0,
}
_FALLBACK = 600.0

_SET_BY_TYPE = sa.text(
    "UPDATE owned_shoes SET mileage_limit = :lim "
    "WHERE mileage_limit IS NULL AND shoe_type = :type"
)
_SET_NULL_TYPE = sa.text(
    "UPDATE owned_shoes SET mileage_limit = :lim "
    "WHERE mileage_limit IS NULL AND shoe_type IS NULL"
)


def upgrade() -> None:
    bind = op.get_bind()
    # FIRST inspect the actual values so the backfill matches reality (and any
    # off-vocabulary/legacy type still gets the fallback, never left NULL).
    types = [row[0] for row in bind.execute(
        sa.text("SELECT DISTINCT shoe_type FROM owned_shoes WHERE mileage_limit IS NULL")
    )]
    for t in types:
        if t is None:
            bind.execute(_SET_NULL_TYPE, {"lim": _FALLBACK})
        else:
            bind.execute(_SET_BY_TYPE, {"lim": _DEFAULTS.get(t, _FALLBACK), "type": t})


def downgrade() -> None:
    # Restore NULL only where the value still equals the default we set, guarded
    # by shoe_type so a legitimately user-set limit that differs is untouched.
    bind = op.get_bind()
    for t, lim in _DEFAULTS.items():
        bind.execute(
            sa.text(
                "UPDATE owned_shoes SET mileage_limit = NULL "
                "WHERE shoe_type = :type AND mileage_limit = :lim"
            ),
            {"type": t, "lim": lim},
        )
    # Symmetric catch-all for rows that got the fallback: a NULL shoe_type or any
    # off-vocabulary type (none exist since R2.4, but keeps the reversal total).
    mapped = list(_DEFAULTS.keys())
    placeholders = ", ".join(f":t{i}" for i in range(len(mapped)))
    params = {f"t{i}": t for i, t in enumerate(mapped)}
    params["lim"] = _FALLBACK
    bind.execute(
        sa.text(
            "UPDATE owned_shoes SET mileage_limit = NULL "
            f"WHERE mileage_limit = :lim AND (shoe_type IS NULL OR shoe_type NOT IN ({placeholders}))"
        ),
        params,
    )
