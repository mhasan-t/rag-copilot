import uuid
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_session
from src.modules.auth.auth_dependencies import CurrentUser
from src.modules.copilot.copilot_dependencies import get_copilot_models
from src.modules.copilot.run_service import CopilotModels, RunService
from src.modules.copilot.schemas import RunCreate, RunRead, RunStepRead

type Session = Annotated[AsyncSession, Depends(get_session)]


async def create_run(
    data: RunCreate,
    current_user: CurrentUser,
    session: Session,
    models: Annotated[CopilotModels, Depends(get_copilot_models)],
) -> RunRead:
    return await RunService(session).ask(current_user, data.question, models)


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
