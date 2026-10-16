"""What the copilot reports to OpenTelemetry. Captured by the in-memory providers installed in conftest."""

import json
import logging
from typing import Any

import pytest
from httpx import AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import NumberDataPoint
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import format_trace_id
from pydantic import ValidationError

from src.core.config import Settings
from src.core.logging import JsonFormatter
from tests.copilot_helpers import ask, classify_as, diagnosis_from, proposing, run_steps
from tests.fake_chat_model import ScriptedChatModel
from tests.telemetry_capture import METRICS, SPANS

pytestmark = pytest.mark.usefixtures("copilot_data")


type Points = dict[frozenset[tuple[str, Any]], float]


def _metric(name: str) -> Points:
    """Current value of each data point (counter sum or histogram count), keyed by its attributes."""
    values: Points = {}
    data = METRICS.get_metrics_data()
    for resource_metrics in data.resource_metrics if data else []:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    for point in metric.data.data_points:
                        value = point.value if isinstance(point, NumberDataPoint) else point.count
                        values[frozenset((point.attributes or {}).items())] = value
    return values


def _attributes(span: ReadableSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


def _trace_id(span: ReadableSpan) -> str:
    context = span.get_span_context()
    assert context is not None
    return format_trace_id(context.trace_id)


def _increase(before: Points, after: Points, **attributes: Any) -> float:
    """How much the points matching `attributes` grew; metrics are cumulative across the whole test session."""
    wanted = set(attributes.items())
    return sum(value - before.get(key, 0) for key, value in after.items() if wanted <= key)


async def test_a_run_is_one_trace_shared_by_its_spans_and_its_audit_trail(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel
):
    SPANS.clear()

    run = (await ask(client, regular_headers)).json()

    spans = [span for span in SPANS.get_finished_spans() if _attributes(span).get("copilot.run_id") == run["id"]]
    [root] = [span for span in spans if span.name == "copilot.run"]
    trace_id = _trace_id(root)
    assert {_trace_id(span) for span in spans} == {trace_id}
    names = {span.name for span in spans}
    assert {"copilot.classify", "copilot.gather_evidence", "copilot.diagnose", "copilot.diagnose llm"} <= names
    assert "copilot.gather_evidence metric:latency_p99_seconds" in names

    # LLM spans carry token usage (GenAI semantic conventions).
    [diagnose_llm] = [span for span in spans if span.name == "copilot.diagnose llm"]
    input_tokens = _attributes(diagnose_llm)["gen_ai.usage.input_tokens"]
    assert isinstance(input_tokens, int) and input_tokens > 100
    assert _attributes(diagnose_llm)["gen_ai.usage.output_tokens"] == 10

    # Every audit row points at the same trace, so a step can be opened in Tempo.
    steps = await run_steps(client, regular_headers, run["id"])
    assert {step["trace_id"] for step in steps} == {trace_id}


async def test_failed_steps_are_marked_on_their_span(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel
):
    SPANS.clear()
    llm.handlers["Classification"] = classify_as("investigate", service="inventory")  # unknown to the demo backend

    run = (await ask(client, regular_headers, "Is the inventory service healthy?")).json()

    [deployment] = [
        span
        for span in SPANS.get_finished_spans()
        if span.name == "copilot.gather_evidence deployment" and _attributes(span)["copilot.run_id"] == run["id"]
    ]
    assert deployment.status.status_code == trace.StatusCode.ERROR
    assert [event.name for event in deployment.events] == ["exception"]


async def test_runs_tokens_remediations_and_step_errors_are_counted(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel
):
    before = {name: _metric(name) for name in _METRIC_NAMES}
    llm.handlers["Diagnosis"] = proposing("scale_deployment", replicas=2)
    run = (await ask(client, regular_headers)).json()
    await client.post(f"/v1/remediations/{run['remediation']['id']}/reject", json={}, headers=regular_headers)
    llm.handlers["Classification"] = classify_as("investigate", service="inventory")
    llm.handlers["Diagnosis"] = diagnosis_from  # no proposal this time
    await ask(client, regular_headers, "Is the inventory service healthy?")
    after = {name: _metric(name) for name in _METRIC_NAMES}

    def increase(name: str, **attributes: Any) -> float:
        return _increase(before[name], after[name], **attributes)

    assert increase("copilot.runs", status="awaiting_approval") == 1
    assert increase("copilot.runs", status="rejected") == 1
    assert increase("copilot.runs", status="completed") == 1  # the inventory run
    assert increase("copilot.remediation.events", event="proposed", action="scale_deployment", risk="low") == 1
    assert increase("copilot.remediation.events", event="rejected") == 1
    assert increase("copilot.llm.tokens", node="diagnose", type="input") > 100
    assert increase("copilot.llm.tokens", node="classify", type="output") == 20  # two runs, 10 each
    assert increase("copilot.step.duration", node="gather_evidence", tool="deployment", error=True) == 1
    assert increase("copilot.step.duration", node="diagnose", error=False) == 4  # node + LLM call, two runs


_METRIC_NAMES = ("copilot.runs", "copilot.remediation.events", "copilot.llm.tokens", "copilot.step.duration")


def test_log_lines_carry_the_current_trace_id():
    formatter = JsonFormatter()
    record = logging.makeLogRecord({"msg": "something happened", "levelname": "INFO"})

    assert "trace_id" not in json.loads(formatter.format(record))
    with trace.get_tracer(__name__).start_as_current_span("work") as span:
        line = json.loads(formatter.format(record))

    assert line["trace_id"] == format_trace_id(span.get_span_context().trace_id)
    assert len(line["span_id"]) == 16


def test_telemetry_needs_an_endpoint_only_when_enabled():
    with pytest.raises(ValidationError, match="OTEL_EXPORTER_OTLP_ENDPOINT is required"):
        Settings(telemetry_traces_enabled=True, otel_exporter_otlp_endpoint=None)  # pyright: ignore[reportCallIssue]

    settings = Settings(telemetry_traces_enabled=False, otel_exporter_otlp_endpoint=None)  # pyright: ignore[reportCallIssue]
    assert not settings.telemetry_traces_enabled
