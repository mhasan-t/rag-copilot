import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.core.config import settings
from src.core.database import Base


class Document(Base):
    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    title: Mapped[str] = mapped_column(String(255))
    source_uri: Mapped[str] = mapped_column(
        String(1024), unique=True, comment="Identity of the source; re-ingesting the same URI replaces the document"
    )
    doc_type: Mapped[str] = mapped_column(String(16), comment="runbook, postmortem or wiki")
    service_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(63)), server_default=text("'{}'"), comment="Services this applies to; empty means all services"
    )
    content_hash: Mapped[str] = mapped_column(
        String(64), comment="SHA-256 of everything that was ingested; unchanged hash means re-ingestion is a no-op"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunk"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index(
            "ix_document_chunk_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer, comment="Position of the chunk within its document")
    content: Mapped[str] = mapped_column(Text, comment="Heading path line, blank line, then the section text")
    embedding: Mapped[list[float]] = mapped_column(
        # Size is fixed by the migration; the API refuses to start if EMBEDDING_DIMENSIONS no longer matches.
        Vector(settings.embedding_dimensions)
    )
    embedding_model: Mapped[str] = mapped_column(
        String(255), comment="provider:model that produced the embedding; vectors from different models can't be mixed"
    )
