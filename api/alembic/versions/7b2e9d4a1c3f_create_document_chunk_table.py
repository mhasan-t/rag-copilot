"""create document_chunk table

Revision ID: 7b2e9d4a1c3f
Revises: df1adc15da6c
Create Date: 2026-10-12 08:50:45.622117

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op
from src.core.config import settings

# revision identifiers, used by Alembic.
revision: str = "7b2e9d4a1c3f"
down_revision: str | Sequence[str] | None = "df1adc15da6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "document_chunk",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, comment="Position of the chunk within its document"),
        sa.Column("content", sa.Text(), nullable=False, comment="Heading path line, blank line, then the section text"),
        # Sized for the embedding model configured when this migration runs; changing models later needs a new
        # migration that resizes the column, plus a re-ingest.
        sa.Column("embedding", Vector(settings.embedding_dimensions), nullable=False),
        sa.Column(
            "embedding_model",
            sa.String(length=255),
            nullable=False,
            comment="provider:model that produced the embedding; vectors from different models can't be mixed",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.id"], name=op.f("fk_document_chunk_document_id_document"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunk")),
        sa.UniqueConstraint("document_id", "chunk_index", name=op.f("uq_document_chunk_document_id_chunk_index")),
    )
    op.create_index(
        "ix_document_chunk_embedding",
        "document_chunk",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_document_chunk_embedding", table_name="document_chunk")
    op.drop_table("document_chunk")
