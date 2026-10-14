import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.trace import format_trace_id
from pydantic_core import to_jsonable_python

from src.core.database import session_factory
from src.core.exceptions import AppError
from src.modules.copilot.run_repository import RunRepository

_tracer = trace.get_tracer(__name__)
_step_duration = metrics.get_meter(__name__).create_histogram(
    "copilot.step.duration", unit="ms", description="Duration of copilot graph nodes, tool queries and LLM calls"
)


class OpenStep:
    """Handed to the body of `RunStepService.track`; set `output` to have it recorded."""

    output: Any = None


class RunStepService:
    """Writes a run's audit trail as it happens, one committed row per step, and traces each step as a span.

    Each step uses its own short session, so steps of parallel nodes can be written concurrently and a step
    stays recorded even if the run fails later.
    """

    def __init__(self, run_id: uuid.UUID):
        self._run_id = run_id

    @asynccontextmanager
    async def track(self, node: str, tool_name: str | None = None, input: Any = None) -> AsyncIterator[OpenStep]:
        """Times the body and records it as a step; a raised exception is recorded and re-raised.

        The body runs inside the step's span, so it can add attributes (e.g. token usage) to the current span.
        """
        attributes = {"copilot.run_id": str(self._run_id), "copilot.node": node}
        if tool_name:
            attributes["copilot.tool"] = tool_name
        span_name = f"copilot.{node}" + (f" {tool_name}" if tool_name else "")
        with _tracer.start_as_current_span(span_name, attributes=attributes) as span:
            step = OpenStep()
            started = time.perf_counter()
            try:
                yield step
            except Exception as exc:
                await self._save(span, node, tool_name, input, None, _describe(exc), started)
                raise
            await self._save(span, node, tool_name, input, step.output, None, started)

    async def _save(
        self,
        span: trace.Span,
        node: str,
        tool_name: str | None,
        input: Any,
        output: Any,
        error: str | None,
        started: float,
    ) -> None:
        duration_ms = round((time.perf_counter() - started) * 1000)
        labels = {"node": node, "error": error is not None} | ({"tool": tool_name} if tool_name else {})
        _step_duration.record(duration_ms, labels)
        span_context = span.get_span_context()
        async with session_factory() as session:
            await RunRepository(session).add_step(
                run_id=self._run_id,
                node=node,
                tool_name=tool_name,
                input=to_jsonable_python(input),
                output=to_jsonable_python(output),
                error=error,
                duration_ms=duration_ms,
                trace_id=format_trace_id(span_context.trace_id) if span_context.is_valid else None,
            )
            await session.commit()


def _describe(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return f"{exc.message} {exc.details}" if exc.details else exc.message
    return type(exc).__name__
