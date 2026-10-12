from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_redis, get_session
from src.modules.health.health_service import HealthService, HealthStatus


async def get_health(
    session: Annotated[AsyncSession, Depends(get_session)], redis: Annotated[Redis, Depends(get_redis)]
) -> HealthStatus:
    return await HealthService(session, redis).check()
