import hashlib
from typing import cast

from langchain_core.embeddings import Embeddings
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import app_config, settings
from src.core.exceptions import ConflictError, ForbiddenError, InvalidInputError, UpstreamError
from src.core.logging import logger
from src.core.validation import require_service_name
from src.modules.auth.schemas import UserRead
from src.modules.knowledge.chunking import chunk_markdown
from src.modules.knowledge.knowledge_policy import KnowledgePolicy
from src.modules.knowledge.knowledge_query import KnowledgeQuery
from src.modules.knowledge.knowledge_repository import KnowledgeRepository
from src.modules.knowledge.schemas import DocType, DocumentIngest, IngestResult, SearchHit

EMBEDDING_MODEL_ID = f"{settings.embedding_provider}:{settings.embedding_model}"


class KnowledgeService:
    def __init__(self, session: AsyncSession, embeddings: Embeddings):
        self._session = session
        self._embeddings = embeddings
        self._query = KnowledgeQuery(session)
        self._repository = KnowledgeRepository(session)

    async def ingest_as(self, actor: UserRead, data: DocumentIngest) -> IngestResult:
        # Ingested text is later fed to the LLM, so who may add it is restricted.
        if not KnowledgePolicy(actor).can_ingest():
            raise ForbiddenError("Only superusers can ingest documents")
        logger.info("document ingestion requested", extra={"source_uri": data.source_uri, "actor_id": actor.id})
        return await self.ingest(data)

    async def ingest(self, data: DocumentIngest) -> IngestResult:
        """Creates or replaces the document identified by `source_uri`; a no-op when nothing changed."""
        content_hash = hashlib.sha256(data.model_dump_json().encode()).hexdigest()
        existing = await self._query.get_by_source_uri(data.source_uri)
        if existing is not None and existing.content_hash == content_hash:
            chunk_count = await self._query.count_chunks(existing)
            return IngestResult(
                document_id=existing.id, source_uri=data.source_uri, result="unchanged", chunk_count=chunk_count
            )

        chunks = chunk_markdown(data.title, data.content)
        if not chunks:
            raise InvalidInputError("Document has no text to index")
        # Embed before writing anything, so a provider failure leaves the stored document untouched.
        vectors = await self._embed(chunks)

        values = data.model_dump(exclude={"content"}) | {"content_hash": content_hash}
        try:
            if existing is None:
                document = await self._repository.create_document(**values)
            else:
                document = await self._repository.update_document(existing, **values)
            await self._repository.replace_chunks(
                document.id,
                [
                    {"chunk_index": index, "content": chunk, "embedding": vector, "embedding_model": EMBEDDING_MODEL_ID}
                    for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
                ],
            )
            await self._session.commit()
        except IntegrityError as exc:
            # Two concurrent ingests of the same new source_uri.
            await self._session.rollback()
            raise ConflictError("Document is being ingested concurrently; retry") from exc

        result = IngestResult(
            document_id=document.id,
            source_uri=data.source_uri,
            result="created" if existing is None else "updated",
            chunk_count=len(chunks),
        )
        logger.info("document ingested", extra=result.model_dump())
        return result

    async def search(self, query: str, service: str | None = None, limit: int | None = None) -> list[SearchHit]:
        """Most relevant chunks for `query`; with `service`, only that service's documents and untagged ones."""
        if service is not None:
            require_service_name(service)
        [vector] = await self._embed([query], is_query=True)
        rows = await self._query.search(vector, service, limit or app_config.knowledge.top_k)
        hits = [
            SearchHit(
                document_id=document.id,
                title=document.title,
                source_uri=document.source_uri,
                doc_type=cast(DocType, document.doc_type),  # only DocType values are ever stored
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=1 - distance,
            )
            for chunk, document, distance in rows
        ]
        logger.info("knowledge searched", extra={"service": service, "hits": len(hits)})
        return hits

    async def _embed(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        """Some models embed search queries differently from documents, hence the separate query call."""
        # Each provider raises its own exception types; all of them mean the same thing to our callers.
        try:
            if is_query:
                vectors = [await self._embeddings.aembed_query(texts[0])]
            else:
                vectors = await self._embeddings.aembed_documents(texts)
        except Exception as exc:
            raise UpstreamError("Embedding provider failed", details={"error": type(exc).__name__}) from exc
        if any(len(vector) != settings.embedding_dimensions for vector in vectors):
            raise UpstreamError(
                f"Embedding model returned {len(vectors[0])} dimensions; EMBEDDING_DIMENSIONS is "
                f"{settings.embedding_dimensions}"
            )
        return vectors


async def verify_embedding_index(session: AsyncSession) -> None:
    """Refuses to start if stored vectors can't be compared with what the configured model produces."""
    query = KnowledgeQuery(session)
    if (stored := await query.embedding_dimensions()) != settings.embedding_dimensions:
        raise RuntimeError(
            f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions} but the index stores {stored}-dimension vectors. "
            "Changing the embedding model needs a migration that resizes document_chunk.embedding and a re-ingest."
        )
    if (other := await query.other_embedding_model(EMBEDDING_MODEL_ID)) is not None:
        raise RuntimeError(
            f"The index holds vectors from {other}, but the configured embedding model is {EMBEDDING_MODEL_ID}. "
            "Re-ingest all documents with the new model (or switch back)."
        )
