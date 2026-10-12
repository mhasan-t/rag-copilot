import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ServiceUnavailableError

CHECK_TIMEOUT_SECONDS = 2


class HealthStatus(BaseModel):
    status: Literal["ok"]
    checks: dict[str, str]


class HealthService:
    """Readiness: verifies every backing service the API cannot work without."""

    def __init__(self, session: AsyncSession, redis: Redis):
        self._session = session
        self._redis = redis

    async def check(self) -> HealthStatus:
        checks = {
            "database": await self._run_check(self._ping_database),
            "redis": await self._run_check(self._redis.ping),
        }
        if any(result != "ok" for result in checks.values()):
            raise ServiceUnavailableError("One or more dependencies are unavailable", details=checks)
        return HealthStatus(status="ok", checks=checks)

    async def _ping_database(self) -> None:
        await self._session.execute(text("SELECT 1"))

    @staticmethod
    async def _run_check(probe: Callable[[], Awaitable[object]]) -> str:
        # Failures become part of the 503 details instead of aborting the remaining checks.
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
                await probe()
        except Exception as exc:
            return f"unavailable: {type(exc).__name__}"
        return "ok"
