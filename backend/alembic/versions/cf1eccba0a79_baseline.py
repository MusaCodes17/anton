"""baseline

Revision ID: cf1eccba0a79
Revises:
Create Date: 2026-07-02

Empty baseline — the existing DB was created by init_db() + the nine
migrate_add_*.py scripts. This revision marks the starting point for
Alembic management without trying to re-apply those changes.
Stamp the DB with:  alembic stamp cf1eccba0a79
"""
from typing import Sequence, Union

revision: str = 'cf1eccba0a79'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
