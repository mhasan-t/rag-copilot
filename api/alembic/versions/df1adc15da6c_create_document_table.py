"""create document table

Revision ID: df1adc15da6c
Revises: f3e9c4316f53
Create Date: 2026-10-12 08:50:45.622117

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "df1adc15da6c"
down_revision: str | Sequence[str] | None = "f3e9c4316f53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "document",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "source_uri",
            sa.String(length=1024),
            nullable=False,
            comment="Identity of the source; re-ingesting the same URI replaces the document",
        ),
        sa.Column("doc_type", sa.String(length=16), nullable=False, comment="runbook, postmortem or wiki"),
        sa.Column(
            "service_tags",
            postgresql.ARRAY(sa.String(length=63)),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Services this applies to; empty means all services",
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 of everything that was ingested; unchanged hash means re-ingestion is a no-op",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document")),
        sa.UniqueConstraint("source_uri", name=op.f("uq_document_source_uri")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("document")
