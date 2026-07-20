"""SPA session-cookie table (RA2.1).

Adds one table for the password-login session cookie that replaces the baked-in
`spa` bearer token in the SPA build:
  - sessions   hashed session ids with an expiry

No data is moved; downgrade drops the table (safe since it starts empty).
Pre-migration backup is not required — purely additive schema with no existing
data, so the E4 ceremony is not triggered (E4-light).

Revision ID: 1a2b3c4d5e6f
Revises:     a2b3c4d5e6f7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1a2b3c4d5e6f"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        # SHA-256 hex of the >=256-bit random session id (raw value lives only
        # in the browser cookie — same discipline as oauth_tokens).
        sa.Column("session_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_hash"),
    )


def downgrade() -> None:
    op.drop_table("sessions")
