import math
from datetime import UTC, datetime

from src.core.http import request_json
from src.modules.monitoring.schemas import MetricPoint


class PrometheusAdapter:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def query_range(self, query: str, start: datetime, end: datetime, step_seconds: int) -> list[MetricPoint]:
        """Runs a PromQL range query that must aggregate to a single series; returns its points."""
        body = await request_json(
            "GET",
            f"{self._base_url}/api/v1/query_range",
            upstream="prometheus",
            params={"query": query, "start": start.timestamp(), "end": end.timestamp(), "step": step_seconds},
        )
        series = body["data"]["result"]
        if not series:
            return []
        return [
            MetricPoint(timestamp=datetime.fromtimestamp(timestamp, UTC), value=float(value))
            for timestamp, value in series[0]["values"]
            # e.g. a quantile over zero requests is NaN; it means "no data", and NaN isn't valid JSON.
            if not math.isnan(float(value))
        ]
