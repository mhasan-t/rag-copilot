import asyncio
from collections.abc import Coroutine
from typing import Any

from src.core.logging import logger

# References keep running tasks from being garbage-collected mid-flight.
_tasks: set[asyncio.Task[Any]] = set()


def spawn(coroutine: Coroutine[Any, Any, Any], name: str) -> None:
    """Runs work after the response is sent, independent of the request.

    ponytail: in-process tasks die with the process, so a restart mid-task loses that work; the upgrade path is a
    durable job queue that resumes it.
    """
    task = asyncio.create_task(coroutine, name=name)
    _tasks.add(task)
    task.add_done_callback(_on_done)


async def wait_for_all() -> None:
    """For tests and graceful shutdown: waits until no background task is running."""
    while _tasks:
        await asyncio.gather(*_tasks, return_exceptions=True)


def _on_done(task: asyncio.Task[Any]) -> None:
    _tasks.discard(task)
    # No request is attached, so the global exception handler never sees these failures.
    if not task.cancelled() and (exc := task.exception()) is not None:
        logger.error("background task failed", exc_info=exc, extra={"task": task.get_name()})
