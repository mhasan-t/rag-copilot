import uuid
from typing import Annotated

from fastapi import Depends, Query
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_session
from src.modules.auth.auth_dependencies import CurrentUser
from src.modules.copilot.copilot_dependencies import get_chat_model, get_classifier_model
from src.modules.copilot.run_service import RunService
from src.modules.copilot.schemas import RunCreate, RunRead, RunStepRead
from src.modules.knowledge.knowledge_dependencies import get_embeddings

type Session = Annotated[AsyncSession, Depends(get_session)]


async def create_run(
    data: RunCreate,
    current_user: CurrentUser,
    session: Session,
    chat_model: Annotated[BaseChatModel, Depends(get_chat_model)],
    classifier_model: Annotated[BaseChatModel, Depends(get_classifier_model)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
) -> RunRead:
    return await RunService(session).ask(current_user, data.question, chat_model, classifier_model, embeddings)


async def list_runs(
    current_user: CurrentUser,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RunRead]:
    return await RunService(session).list(current_user, limit, offset)


async def get_run(run_id: uuid.UUID, current_user: CurrentUser, session: Session) -> RunRead:
    return await RunService(session).get(current_user, run_id)


async def list_run_steps(run_id: uuid.UUID, current_user: CurrentUser, session: Session) -> list[RunStepRead]:
    return await RunService(session).list_steps(current_user, run_id)
