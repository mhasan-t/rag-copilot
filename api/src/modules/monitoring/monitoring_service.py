from datetime import UTC, datetime, timedelta
from string import Template

from src.core.config import MetricName, app_config, settings
from src.core.exceptions import InvalidInputError
from src.core.logging import logger
from src.core.validation import require_service_name
from src.modules.monitoring.loki_adapter import LokiAdapter
from src.modules.monitoring.prometheus_adapter import PrometheusAdapter
from src.modules.monitoring.schemas import LogEntry, MetricSeries, TraceSummary
from src.modules.monitoring.tempo_adapter import TempoAdapter

MAX_WINDOW_MINUTES = 24 * 60
# About this many points per series: enough to see a spike, small enough to hand to an LLM.
TARGET_POINTS = 60


class MonitoringService:
    """Evidence-gathering queries over the monitoring stack, built only from the templates in config/app.yaml."""

    def __init__(self) -> None:
        self._prometheus = PrometheusAdapter(settings.prometheus_url)
        self._loki = LokiAdapter(settings.loki_url)
        self._tempo = TempoAdapter(settings.tempo_url)
        self._templates = app_config.monitoring

    async def get_metric(self, service: str, metric: MetricName, window_minutes: int) -> MetricSeries:
        start, end = self._window(window_minutes)
        step_seconds = max(15, window_minutes * 60 // TARGET_POINTS)
        # The rate window must span at least two scrapes/exports, and never be shorter than the step.
        query = self._render(
            self._templates.metrics[metric], service=service, rate_window=f"{max(60, 2 * step_seconds)}s"
        )
        points = await self._prometheus.query_range(query, start, end, step_seconds)
        logger.info("metric queried", extra={"service": service, "metric": metric, "points": len(points)})
        return MetricSeries(service=service, metric=metric, window_minutes=window_minutes, points=points)

    async def get_error_logs(self, service: str, window_minutes: int, limit: int = 50) -> list[LogEntry]:
        start, end = self._window(window_minutes)
        entries = await self._loki.query_range(
            self._render(self._templates.error_logs, service=service), start, end, limit
        )
        logger.info("error logs queried", extra={"service": service, "entries": len(entries)})
        return entries

    async def get_slow_traces(
        self, service: str, window_minutes: int, min_duration_ms: int = 500, limit: int = 20
    ) -> list[TraceSummary]:
        start, end = self._window(window_minutes)
        query = self._render(self._templates.slow_traces, service=service, min_duration_ms=str(int(min_duration_ms)))
        traces = await self._tempo.search(query, start, end, limit)
        logger.info("slow traces queried", extra={"service": service, "traces": len(traces)})
        return traces

    @staticmethod
    def _render(template: str, service: str, **values: str) -> str:
        return Template(template).substitute(service=require_service_name(service), **values)

    @staticmethod
    def _window(window_minutes: int) -> tuple[datetime, datetime]:
        if not 1 <= window_minutes <= MAX_WINDOW_MINUTES:
            raise InvalidInputError(f"window_minutes must be between 1 and {MAX_WINDOW_MINUTES}")
        end = datetime.now(UTC)
        return end - timedelta(minutes=window_minutes), end
