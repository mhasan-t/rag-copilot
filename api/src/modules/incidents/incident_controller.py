from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_session
from src.core.validation import ServiceName
from src.modules.auth.auth_dependencies import CurrentUser
from src.modules.incidents.incident_service import IncidentService
from src.modules.incidents.schemas import IncidentRead


async def list_incidents(
    _: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    service: ServiceName | None = None,
    since: Annotated[datetime | None, Query(description="Defaults to 30 days ago")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[IncidentRead]:
    return await IncidentService(session).list_recent(service, since, limit)
