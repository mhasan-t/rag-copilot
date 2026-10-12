import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic_core import to_jsonable_python

from src.core.database import session_factory
from src.core.exceptions import AppError
from src.modules.copilot.run_repository import RunRepository


class OpenStep:
    """Handed to the body of `RunStepService.track`; set `output` to have it recorded."""

    output: Any = None


class RunStepService:
    """Writes a run's audit trail as it happens, one committed row per step.

    Each step uses its own short session, so steps of parallel nodes can be written concurrently and a step
    stays recorded even if the run fails later.
    """

    def __init__(self, run_id: uuid.UUID):
        self._run_id = run_id

    @asynccontextmanager
    async def track(self, node: str, tool_name: str | None = None, input: Any = None) -> AsyncIterator[OpenStep]:
        """Times the body and records it as a step; a raised exception is recorded and re-raised."""
        step = OpenStep()
        started = time.perf_counter()
        try:
            yield step
        except Exception as exc:
            await self._save(node, tool_name, input, None, _describe(exc), started)
            raise
        await self._save(node, tool_name, input, step.output, None, started)

    async def _save(
        self, node: str, tool_name: str | None, input: Any, output: Any, error: str | None, started: float
    ) -> None:
        async with session_factory() as session:
            await RunRepository(session).add_step(
                run_id=self._run_id,
                node=node,
                tool_name=tool_name,
                input=to_jsonable_python(input),
                output=to_jsonable_python(output),
                error=error,
                duration_ms=round((time.perf_counter() - started) * 1000),
            )
            await session.commit()


def _describe(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return f"{exc.message} {exc.details}" if exc.details else exc.message
    return type(exc).__name__
