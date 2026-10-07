"""coros_connection + coros_oauth_states (COROS direct sync §2, roadmap R5.7)

Revision ID: 7a8b9c0d1e2f
Revises: 2b3c4d5e6f7a
Create Date: 2026-10-07

Additive only (two new tables, no data moved), so the full E4 bar (backup +
reconciliation) does not apply; reversibility is exercised by a down/up
round-trip (see changelog). `coros_connection` is a single-row table (id = 1;
there is no users table to key on). Tokens are Fernet ciphertext — encryption
happens only inside services/coros_connection.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, None] = "2b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coros_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(255), nullable=True),
        sa.Column("registered_redirect_uri", sa.String(2048), nullable=True),
        sa.Column("region_endpoint", sa.String(2048), nullable=True),
        sa.Column("access_token_enc", sa.Text(), nullable=True),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.Float(), nullable=True),
        sa.Column("scopes", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="disconnected"),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_table(
        "coros_oauth_states",
        sa.Column("state", sa.String(100), primary_key=True),
        sa.Column("code_verifier_enc", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("coros_oauth_states")
    op.drop_table("coros_connection")
