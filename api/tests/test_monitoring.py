"""Runs against the live dev stack: the demo payments service, its load generator and the LGTM monitoring stack."""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.config import MetricName, settings
from src.core.exceptions import InvalidInputError, NotFoundError, UpstreamError
from src.modules.deployments.deployment_service import DeploymentService
from src.modules.monitoring.monitoring_service import MonitoringService
from src.modules.monitoring.prometheus_adapter import PrometheusAdapter
from tests.helpers import eventually


async def test_bad_release_shows_up_in_every_evidence_source(bad_release: None):
    monitoring = MonitoringService()

    deployment = await DeploymentService().get_deployment("payments")
    assert deployment.version == "v2"
    assert deployment.history[0].version == "v2"
    assert len(deployment.history) >= 2

    async def latency_spiked() -> None:
        series = await monitoring.get_metric("payments", MetricName.LATENCY_P99_SECONDS, 5)
        assert series.points and series.points[-1].value > 0.5  # v1 stays under ~0.1 s

    async def errors_rose() -> None:
        series = await monitoring.get_metric("payments", MetricName.ERROR_RATIO, 5)
        assert series.points and series.points[-1].value > 0.01

    async def error_logs_name_the_cause() -> None:
        logs = await monitoring.get_error_logs("payments", 5)
        assert any("connection pool exhausted" in entry.message and entry.severity == "ERROR" for entry in logs)

    async def slow_traces_found() -> None:
        traces = await monitoring.get_slow_traces("payments", 5, min_duration_ms=500)
        assert traces and all(trace.duration_ms >= 500 for trace in traces)
        assert traces[0].root_name == "POST /payments"

    for check in (latency_spiked, errors_rose, error_logs_name_the_cause, slow_traces_found):
        await eventually(check)


async def test_request_rate_matches_load_generator():
    async def about_five_per_second() -> None:
        series = await MonitoringService().get_metric("payments", MetricName.REQUEST_RATE, 10)
        assert series.points and 3 < series.points[-1].value < 7

    await eventually(about_five_per_second)


async def test_unknown_service_has_no_data():
    monitoring = MonitoringService()

    assert (await monitoring.get_metric("no-such-service", MetricName.REQUEST_RATE, 10)).points == []
    assert await monitoring.get_error_logs("no-such-service", 10) == []
    assert await monitoring.get_slow_traces("no-such-service", 10) == []
    with pytest.raises(NotFoundError):
        await DeploymentService().get_deployment("no-such-service")


@pytest.mark.parametrize("service", ['payments"} or vector(1) or {x="', "Payments", "", "a b"])
async def test_service_names_that_could_alter_a_query_are_rejected(service: str):
    monitoring = MonitoringService()

    with pytest.raises(InvalidInputError):
        await monitoring.get_metric(service, MetricName.REQUEST_RATE, 10)
    with pytest.raises(InvalidInputError):
        await monitoring.get_error_logs(service, 10)
    with pytest.raises(InvalidInputError):
        await monitoring.get_slow_traces(service, 10)
    with pytest.raises(InvalidInputError):
        await DeploymentService().get_deployment(service)


@pytest.mark.parametrize("window_minutes", [0, 24 * 60 + 1])
async def test_window_must_be_between_one_minute_and_one_day(window_minutes: int):
    with pytest.raises(InvalidInputError):
        await MonitoringService().get_metric("payments", MetricName.REQUEST_RATE, window_minutes)


async def test_backend_failures_become_upstream_errors():
    end = datetime.now(UTC)
    start = end - timedelta(minutes=5)

    with pytest.raises(UpstreamError, match="unreachable"):
        await PrometheusAdapter("http://lgtm:1").query_range("up", start, end, 15)
    with pytest.raises(UpstreamError, match="400") as error:
        await PrometheusAdapter(settings.prometheus_url).query_range("sum(", start, end, 15)
    assert "parse error" in error.value.details["response"]
