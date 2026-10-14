import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.core.config import MetricName
from src.core.database import session_factory
from src.core.exceptions import AppError
from src.modules.copilot.run_step_service import RunStepService
from src.modules.copilot.schemas import Evidence
from src.modules.deployments.deployment_service import DeploymentService
from src.modules.deployments.schemas import DeploymentState
from src.modules.incidents.incident_service import IncidentService
from src.modules.monitoring.monitoring_service import MonitoringService
from src.modules.monitoring.schemas import LogEntry, MetricSeries, TraceSummary

NODE = "gather_evidence"


class MonitoringBackend(Protocol):
    async def get_metric(self, service: str, metric: MetricName, window_minutes: int) -> MetricSeries: ...
    async def get_error_logs(self, service: str, window_minutes: int) -> list[LogEntry]: ...
    async def get_slow_traces(self, service: str, window_minutes: int) -> list[TraceSummary]: ...


class DeploymentBackend(Protocol):
    async def get_deployment(self, service: str) -> DeploymentState: ...


@dataclass
class EvidenceBackends:
    """Where live evidence comes from: the real services, or recorded fixtures for the evals."""

    monitoring: MonitoringBackend = field(default_factory=MonitoringService)
    deployments: DeploymentBackend = field(default_factory=DeploymentService)


class EvidenceService:
    """Queries every evidence source for a service in parallel, recording each query as a tool step."""

    def __init__(self, steps: RunStepService, backends: EvidenceBackends | None = None):
        self._steps = steps
        backends = backends or EvidenceBackends()
        self._monitoring = backends.monitoring
        self._deployments = backends.deployments

    async def gather(self, service: str, window_minutes: int) -> Evidence:
        evidence = Evidence(service=service, window_minutes=window_minutes)
        args = {"service": service, "window_minutes": window_minutes}

        async def metric(name: MetricName) -> None:
            evidence.metrics[name] = await self._monitoring.get_metric(service, name, window_minutes)

        async def error_logs() -> None:
            evidence.error_logs = await self._monitoring.get_error_logs(service, window_minutes)

        async def slow_traces() -> None:
            evidence.slow_traces = await self._monitoring.get_slow_traces(service, window_minutes)

        async def deployment() -> None:
            evidence.deployment = await self._deployments.get_deployment(service)

        async def incidents() -> None:
            async with session_factory() as session:
                evidence.incidents = await IncidentService(session).list_recent(service, limit=5)

        sources: dict[str, Callable[[], Awaitable[None]]] = {
            **{f"metric:{name}": (lambda name=name: metric(name)) for name in MetricName},
            "error_logs": error_logs,
            "slow_traces": slow_traces,
            "deployment": deployment,
            "incidents": incidents,
        }
        await asyncio.gather(*(self._fetch(name, fetch, args, evidence) for name, fetch in sources.items()))
        return evidence

    async def _fetch(
        self, name: str, fetch: Callable[[], Awaitable[None]], args: dict[str, Any], evidence: Evidence
    ) -> None:
        # Expected failures (backend down, unknown service) make one source unavailable, not the whole run;
        # anything else is a bug and propagates.
        try:
            async with self._steps.track(NODE, tool_name=name, input=args) as step:
                await fetch()
                step.output = _source_output(name, evidence)
        except AppError as exc:
            evidence.unavailable[name] = exc.message


def _source_output(name: str, evidence: Evidence) -> Any:
    if name.startswith("metric:"):
        return evidence.metrics[MetricName(name.removeprefix("metric:"))]
    return getattr(evidence, name)
