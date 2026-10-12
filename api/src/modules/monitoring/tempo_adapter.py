from datetime import UTC, datetime

from src.core.http import request_json
from src.modules.monitoring.schemas import TraceSummary


class TempoAdapter:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def search(self, traceql: str, start: datetime, end: datetime, limit: int) -> list[TraceSummary]:
        """Runs a TraceQL search; returns matching traces, slowest first."""
        body = await request_json(
            "GET",
            f"{self._base_url}/api/search",
            upstream="tempo",
            params={"q": traceql, "start": int(start.timestamp()), "end": int(end.timestamp()), "limit": limit},
        )
        traces = [
            TraceSummary(
                trace_id=trace["traceID"],
                root_name=trace.get("rootTraceName", "unknown"),
                started_at=datetime.fromtimestamp(int(trace["startTimeUnixNano"]) / 1e9, UTC),
                # Tempo omits durationMs for traces under 1 ms.
                duration_ms=trace.get("durationMs", 0),
            )
            for trace in body.get("traces", [])
        ]
        return sorted(traces, key=lambda trace: trace.duration_ms, reverse=True)
