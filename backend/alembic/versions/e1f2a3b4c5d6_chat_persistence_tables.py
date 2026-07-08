"""add chat persistence tables (conversations + checkpoint prompts)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-08

R2.6 server-side chat & memory persistence. Move Son of Anton conversations and
the 100 km checkpoint-prompt state off browser localStorage into the backend so
memory is device-independent (and later, R3, readable by server-side agents).
The streaming endpoint stays stateless per request; these tables back a separate
CRUD surface.

`chat_conversations.id` is the client-generated UUID (preserves the frontend's
in-memory-first / persist-on-first-message flow). Message arrays are JSON, not a
normalized messages table — display_messages carries pure UI concerns and at
single-user scale normalizing is speculative infra (CLAUDE.md §2.5).

Pure schema add — no data moves; we start fresh (localStorage is not migrated).
Reversible: downgrade drops both tables. (Autogenerate also flagged pre-existing
SQLite type-mapping artifacts on unrelated tables — app_settings/owned_shoes/
shoe_notes — which are noise, not this change; pruned per skill S03.)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_conversations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('model', sa.String(length=60), nullable=True),
        sa.Column('display_messages', sa.JSON(), nullable=False),
        sa.Column('api_messages', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_conversations_id'), 'chat_conversations', ['id'], unique=False)

    op.create_table(
        'checkpoint_prompts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owned_shoe_id', sa.Integer(), nullable=False),
        sa.Column('checkpoint_km', sa.Integer(), nullable=False),
        sa.Column('prompted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['owned_shoe_id'], ['owned_shoes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owned_shoe_id', 'checkpoint_km', name='uq_checkpoint_prompt_shoe_km'),
    )
    op.create_index(op.f('ix_checkpoint_prompts_id'), 'checkpoint_prompts', ['id'], unique=False)
    op.create_index(op.f('ix_checkpoint_prompts_owned_shoe_id'), 'checkpoint_prompts', ['owned_shoe_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_checkpoint_prompts_owned_shoe_id'), table_name='checkpoint_prompts')
    op.drop_index(op.f('ix_checkpoint_prompts_id'), table_name='checkpoint_prompts')
    op.drop_table('checkpoint_prompts')
    op.drop_index(op.f('ix_chat_conversations_id'), table_name='chat_conversations')
    op.drop_table('chat_conversations')
