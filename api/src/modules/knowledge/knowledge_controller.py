from typing import Annotated

from fastapi import Depends, Query
from langchain_core.embeddings import Embeddings
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_session
from src.core.validation import ServiceName
from src.modules.auth.auth_dependencies import CurrentUser
from src.modules.knowledge.knowledge_dependencies import get_embeddings
from src.modules.knowledge.knowledge_service import KnowledgeService
from src.modules.knowledge.schemas import DocumentIngest, IngestResult, SearchHit

type Session = Annotated[AsyncSession, Depends(get_session)]
type EmbeddingsDep = Annotated[Embeddings, Depends(get_embeddings)]


async def ingest_document(
    data: DocumentIngest, current_user: CurrentUser, session: Session, embeddings: EmbeddingsDep
) -> IngestResult:
    return await KnowledgeService(session, embeddings).ingest_as(current_user, data)


async def search(
    _: CurrentUser,
    session: Session,
    embeddings: EmbeddingsDep,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
    service: ServiceName | None = None,
    limit: Annotated[int | None, Query(ge=1, le=20, description="Defaults to knowledge.top_k")] = None,
) -> list[SearchHit]:
    return await KnowledgeService(session, embeddings).search(q, service, limit)
