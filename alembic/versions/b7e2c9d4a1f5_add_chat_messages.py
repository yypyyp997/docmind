"""add chat_messages table for multi-turn conversation memory

Revision ID: b7e2c9d4a1f5
Revises: 39f98038b35a
Create Date: 2026-11-25
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "b7e2c9d4a1f5"
down_revision = "39f98038b35a"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("NOW()")),
    )
    op.create_index(
        "idx_chat_messages_session",
        "chat_messages",
        ["session_id", "created_at"],
    )

def downgrade() -> None:
    op.drop_index("idx_chat_messages_session", table_name="chat_messages")
    op.drop_table("chat_messages")
