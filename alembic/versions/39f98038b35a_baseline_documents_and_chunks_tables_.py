"""baseline: documents and chunks tables with vector extension

Revision ID: 39f98038b35a
Revises:
Create Date: 2026-11-17
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "39f98038b35a"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doc_name", sa.Text(), nullable=False, unique=True),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.Text()),
        sa.Column("ingested_at", sa.TIMESTAMP(), server_default=sa.text("NOW()")),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doc_id", sa.Integer(),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer()),
        sa.Column("extra", sa.JSON(), server_default="{}"),
        sa.Column("embedding", Vector(1024)),
    )
    op.create_index("idx_chunks_doc", "chunks", ["doc_id"])

def downgrade() -> None:
    op.drop_index("idx_chunks_doc", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("documents")
