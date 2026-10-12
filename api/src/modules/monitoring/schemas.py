from datetime import datetime

from pydantic import BaseModel

from src.core.config import MetricName


class MetricPoint(BaseModel):
    timestamp: datetime
    value: float


class MetricSeries(BaseModel):
    service: str
    metric: MetricName
    window_minutes: int
    points: list[MetricPoint]


class LogEntry(BaseModel):
    timestamp: datetime
    severity: str
    message: str
    trace_id: str | None


class TraceSummary(BaseModel):
    trace_id: str
    root_name: str
    started_at: datetime
    duration_ms: int
