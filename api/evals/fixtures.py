"""Recorded evidence, replayed in place of the live monitoring stack and deployment backend.

A fixture is the Evidence gathered for one service at one moment. On replay its timestamps are shifted so the newest
data is "now", so the LLM sees the same picture however long ago it was recorded.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from src.core.config import MetricName
from src.core.exceptions import NotFoundError
from src.modules.copilot.evidence_service import EvidenceBackends
from src.modules.copilot.schemas import Evidence
from src.modules.deployments.schemas import DeploymentState
from src.modules.monitoring.schemas import LogEntry, MetricSeries, TraceSummary

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class EvidenceFixture(BaseModel):
    recorded_at: datetime
    # How the fixture was made, for whoever reads the JSON (e.g. "recorded live" or the transformation applied).
    description: str
    evidence: Evidence


def save_fixture(scenario: str, fixture: EvidenceFixture) -> Path:
    path = FIXTURE_DIR / f"{scenario}.json"
    path.write_text(fixture.model_dump_json(indent=2) + "\n")
    return path


def replay_backends(scenario: str, now: datetime | None = None) -> EvidenceBackends:
    now = now or datetime.now(UTC)
    fixture = EvidenceFixture.model_validate_json((FIXTURE_DIR / f"{scenario}.json").read_text())
    replay = _Replay(_shift(fixture.evidence, now - fixture.recorded_at), now)
    return EvidenceBackends(monitoring=replay, deployments=replay)


def no_live_backends() -> EvidenceBackends:
    """For cases without a scenario: every source answers "no data", so nothing ever reaches the live stack."""
    empty = _Replay(Evidence(service="", window_minutes=0), datetime.now(UTC))
    return EvidenceBackends(monitoring=empty, deployments=empty)


class _Replay:
    """Answers like the live backends would have: only for the recorded service, only within the window asked for."""

    def __init__(self, evidence: Evidence, now: datetime):
        self._evidence = evidence
        self._now = now

    async def get_metric(self, service: str, metric: MetricName, window_minutes: int) -> MetricSeries:
        series = self._evidence.metrics.get(metric) if service == self._evidence.service else None
        points = [p for p in series.points if p.timestamp >= self._since(window_minutes)] if series else []
        return MetricSeries(service=service, metric=metric, window_minutes=window_minutes, points=points)

    async def get_error_logs(self, service: str, window_minutes: int) -> list[LogEntry]:
        if service != self._evidence.service:
            return []
        return [entry for entry in self._evidence.error_logs if entry.timestamp >= self._since(window_minutes)]

    async def get_slow_traces(self, service: str, window_minutes: int) -> list[TraceSummary]:
        if service != self._evidence.service:
            return []
        return [trace for trace in self._evidence.slow_traces if trace.started_at >= self._since(window_minutes)]

    async def get_deployment(self, service: str) -> DeploymentState:
        if service != self._evidence.service or self._evidence.deployment is None:
            raise NotFoundError("deployment backend: not found", details={"service": service})
        return self._evidence.deployment

    def _since(self, window_minutes: int) -> datetime:
        return self._now - timedelta(minutes=window_minutes)


def _shift(evidence: Evidence, delta: timedelta) -> Evidence:
    shifted = evidence.model_copy(deep=True)
    for series in shifted.metrics.values():
        for point in series.points:
            point.timestamp += delta
    for entry in shifted.error_logs:
        entry.timestamp += delta
    for trace in shifted.slow_traces:
        trace.started_at += delta
    if shifted.deployment is not None:
        for revision in shifted.deployment.history:
            revision.deployed_at += delta
    return shifted
