from collections.abc import Sequence

from sqlalchemy import Row, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.knowledge.models import Document, DocumentChunk


class KnowledgeQuery:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_source_uri(self, source_uri: str) -> Document | None:
        return await self._session.scalar(select(Document).where(Document.source_uri == source_uri))

    async def count_chunks(self, document: Document) -> int:
        statement = select(func.count()).where(DocumentChunk.document_id == document.id)
        return await self._session.scalar(statement) or 0

    async def search(
        self, embedding: list[float], service: str | None, limit: int
    ) -> Sequence[Row[tuple[DocumentChunk, Document, float]]]:
        """Nearest chunks by cosine distance, optionally limited to one service's documents plus untagged ones."""
        # Without this, HNSW filters *after* fetching its candidate list, so a service filter can return fewer
        # than `limit` rows even when more matches exist (pgvector >= 0.8). Scoped to this transaction.
        await self._session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        distance = DocumentChunk.embedding.cosine_distance(embedding).label("distance")
        statement = select(DocumentChunk, Document, distance).join(Document).order_by(distance).limit(limit)
        if service is not None:
            statement = statement.where(
                or_(Document.service_tags.contains([service]), func.cardinality(Document.service_tags) == 0)
            )
        return (await self._session.execute(statement)).all()

    async def embedding_dimensions(self) -> int:
        """Size of the vector column as created by the migrations (pgvector stores it in atttypmod)."""
        statement = text(
            "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'document_chunk'::regclass AND attname = 'embedding'"
        )
        return await self._session.scalar(statement)

    async def other_embedding_model(self, current_model: str) -> str | None:
        """Any embedding model stored in the index other than `current_model`."""
        statement = select(DocumentChunk.embedding_model).where(DocumentChunk.embedding_model != current_model)
        return await self._session.scalar(statement.limit(1))
