from datetime import UTC, datetime

from src.core.http import request_json
from src.modules.monitoring.schemas import LogEntry


class LokiAdapter:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def query_range(self, query: str, start: datetime, end: datetime, limit: int) -> list[LogEntry]:
        """Runs a LogQL log query; returns the newest `limit` entries, newest first."""
        body = await request_json(
            "GET",
            f"{self._base_url}/loki/api/v1/query_range",
            upstream="loki",
            params={
                "query": query,
                "start": _to_nanoseconds(start),
                "end": _to_nanoseconds(end),
                "limit": limit,
                "direction": "backward",
            },
        )
        # OTel attributes become per-line metadata, so nearly every line is its own stream; flatten and re-sort.
        entries = [
            LogEntry(
                timestamp=datetime.fromtimestamp(int(timestamp) / 1e9, UTC),
                severity=stream["stream"].get("severity_text", "UNKNOWN"),
                message=line,
                trace_id=stream["stream"].get("trace_id"),
            )
            for stream in body["data"]["result"]
            for timestamp, line in stream["values"]
        ]
        return sorted(entries, key=lambda entry: entry.timestamp, reverse=True)[:limit]


def _to_nanoseconds(moment: datetime) -> int:
    return int(moment.timestamp() * 1e9)
