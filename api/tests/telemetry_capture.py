"""Real OpenTelemetry SDK providers that keep everything in memory, installed once for the test session.

The app's tracers and instruments report here, so tests can inspect spans and metrics.
"""

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

SPANS = InMemorySpanExporter()
METRICS = InMemoryMetricReader()

_tracer_provider = TracerProvider()
_tracer_provider.add_span_processor(SimpleSpanProcessor(SPANS))
trace.set_tracer_provider(_tracer_provider)
metrics.set_meter_provider(MeterProvider(metric_readers=[METRICS]))
