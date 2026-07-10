"""OAuth 2.1 authorization-server tables (RA1.1b).

Adds two tables for the single-user OAuth server that replaces the
capability-URL connector auth (RA1.1 Path 2 → Path 1):
  - oauth_auth_codes  short-lived PKCE authorization codes
  - oauth_tokens      hashed access tokens and refresh tokens

No data is moved; downgrade drops both tables (safe since they start empty).
Pre-migration backup is not required — purely additive schema with no
existing data, so the E4 ceremony is not triggered.

Revision ID: 0b1c2d3e4f5a
Revises:     f2a3b4c5d6e7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0b1c2d3e4f5a"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_auth_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("code_challenge", sa.String(255), nullable=False),
        sa.Column("redirect_uri", sa.String(2048), nullable=False),
        sa.Column("redirect_uri_provided_explicitly", sa.Boolean(), nullable=False),
        sa.Column("scopes", sa.String(500), nullable=True),
        sa.Column("resource", sa.String(2048), nullable=True),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )

    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("token_type", sa.String(20), nullable=False),  # 'access' | 'refresh'
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("scopes", sa.String(500), nullable=True),
        sa.Column("expires_at", sa.Float(), nullable=True),
        sa.Column("resource", sa.String(2048), nullable=True),
        sa.Column("subject", sa.String(255), nullable=True),
        # pair_id ties an access+refresh pair so revoking one revokes both.
        sa.Column("pair_id", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )


def downgrade() -> None:
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_auth_codes")
