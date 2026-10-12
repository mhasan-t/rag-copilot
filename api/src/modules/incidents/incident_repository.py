from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.incidents.models import Incident


class IncidentRepository:
    """Writes only; the calling service owns the transaction and commits."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_many(self, rows: list[dict[str, Any]]) -> list[Incident]:
        incidents = [Incident(**row) for row in rows]
        self._session.add_all(incidents)
        await self._session.flush()
        return incidents
