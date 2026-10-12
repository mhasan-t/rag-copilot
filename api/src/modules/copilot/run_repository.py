from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.copilot.models import CopilotRun, RunStep


class RunRepository:
    """Writes only; the calling service owns the transaction and commits."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_run(self, **values: Any) -> CopilotRun:
        run = CopilotRun(**values)
        self._session.add(run)
        await self._session.flush()
        await self._session.refresh(run)
        return run

    async def update_run(self, run: CopilotRun, **values: Any) -> CopilotRun:
        for field, value in values.items():
            setattr(run, field, value)
        await self._session.flush()
        await self._session.refresh(run)
        return run

    async def add_step(self, **values: Any) -> None:
        self._session.add(RunStep(**values))
        await self._session.flush()
