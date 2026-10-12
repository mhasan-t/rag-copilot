from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import logger
from src.core.validation import require_service_name
from src.modules.incidents.incident_query import IncidentQuery
from src.modules.incidents.incident_repository import IncidentRepository
from src.modules.incidents.schemas import IncidentCreate, IncidentRead

DEFAULT_LOOKBACK = timedelta(days=30)


class IncidentService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._query = IncidentQuery(session)
        self._repository = IncidentRepository(session)

    async def list_recent(
        self, service: str | None = None, since: datetime | None = None, limit: int = 20
    ) -> list[IncidentRead]:
        """Newest first; `since` defaults to 30 days ago."""
        if service is not None:
            require_service_name(service)
        since = since or datetime.now(UTC) - DEFAULT_LOOKBACK
        incidents = await self._query.list_recent(service, since, limit)
        logger.info("incidents queried", extra={"service": service, "since": since, "count": len(incidents)})
        return [IncidentRead.model_validate(incident) for incident in incidents]

    async def seed(self, incidents: list[IncidentCreate]) -> int:
        """Loads example incidents into an empty table; returns how many were added (0 if it wasn't empty)."""
        if await self._query.count() > 0:
            return 0
        await self._repository.create_many([incident.model_dump() for incident in incidents])
        await self._session.commit()
        logger.info("incidents seeded", extra={"count": len(incidents)})
        return len(incidents)
