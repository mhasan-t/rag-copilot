import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.copilot.models import CopilotRun, RunStep


class RunQuery:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, run_id: uuid.UUID) -> CopilotRun | None:
        return await self._session.get(CopilotRun, run_id)

    async def list(self, user_id: uuid.UUID | None, limit: int, offset: int) -> Sequence[CopilotRun]:
        """Newest first; `user_id=None` lists everyone's runs."""
        statement = select(CopilotRun).order_by(CopilotRun.created_at.desc(), CopilotRun.id)
        if user_id is not None:
            statement = statement.where(CopilotRun.user_id == user_id)
        return (await self._session.scalars(statement.limit(limit).offset(offset))).all()

    async def list_steps(self, run_id: uuid.UUID) -> Sequence[RunStep]:
        statement = select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.created_at, RunStep.id)
        return (await self._session.scalars(statement)).all()
