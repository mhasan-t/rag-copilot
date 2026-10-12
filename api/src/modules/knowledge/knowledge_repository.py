import uuid
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.knowledge.models import Document, DocumentChunk


class KnowledgeRepository:
    """Writes only; the calling service owns the transaction and commits."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_document(self, **values: Any) -> Document:
        document = Document(**values)
        self._session.add(document)
        await self._session.flush()
        await self._session.refresh(document)
        return document

    async def update_document(self, document: Document, **values: Any) -> Document:
        for field, value in values.items():
            setattr(document, field, value)
        await self._session.flush()
        await self._session.refresh(document)
        return document

    async def replace_chunks(self, document_id: uuid.UUID, chunks: list[dict[str, Any]]) -> None:
        await self._session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        self._session.add_all(DocumentChunk(document_id=document_id, **chunk) for chunk in chunks)
        await self._session.flush()
