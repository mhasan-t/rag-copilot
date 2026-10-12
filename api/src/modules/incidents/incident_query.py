from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.incidents.models import Incident


class IncidentQuery:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_recent(self, service: str | None, since: datetime, limit: int) -> Sequence[Incident]:
        statement = select(Incident).where(Incident.started_at >= since)
        if service is not None:
            statement = statement.where(Incident.service == service)
        statement = statement.order_by(Incident.started_at.desc()).limit(limit)
        return (await self._session.scalars(statement)).all()

    async def count(self) -> int:
        return await self._session.scalar(select(func.count()).select_from(Incident)) or 0
