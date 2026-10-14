import logging

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.core.config import app_config, settings
from src.core.database import engine

METRIC_EXPORT_INTERVAL_MS = 10_000

_providers: list[TracerProvider | MeterProvider | LoggerProvider] = []


def configure_telemetry(app: FastAPI) -> None:
    """Exports the API's traces, metrics and logs over OTLP when TELEMETRY_TRACES_ENABLED is set.

    Must run after logging is configured, since it adds a handler to the root logger. When disabled, the
    OpenTelemetry API stays a no-op, so the spans and metrics recorded throughout the code cost nothing.
    """
    if not settings.telemetry_traces_enabled:
        return
    endpoint = (settings.otel_exporter_otlp_endpoint or "").rstrip("/")
    resource = Resource.create({"service.name": app_config.service.name, "service.version": app_config.version})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(tracer_provider)

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"), export_interval_millis=METRIC_EXPORT_INTERVAL_MS
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs")))
    set_logger_provider(logger_provider)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=logger_provider))

    FastAPIInstrumentor.instrument_app(app, excluded_urls="/v1/health")
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    # Covers calls to the monitoring stack, the deployment backend and most LLM provider SDKs.
    HTTPXClientInstrumentor().instrument()
    _providers.extend([tracer_provider, meter_provider, logger_provider])


def shutdown_telemetry() -> None:
    """Flushes buffered spans, metrics and logs; call on shutdown so the last ones aren't lost."""
    for provider in _providers:
        provider.shutdown()
    _providers.clear()
