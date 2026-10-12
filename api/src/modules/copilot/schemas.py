import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.core.config import MetricName
from src.modules.deployments.schemas import DeploymentState
from src.modules.incidents.schemas import IncidentRead
from src.modules.monitoring.schemas import LogEntry, MetricSeries, TraceSummary


class RunCreate(BaseModel):
    question: Annotated[str, Field(min_length=3, max_length=2000)]


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    question: str
    status: Literal["running", "completed", "failed"]
    classification: dict[str, Any] | None
    answer: str | None
    diagnosis: dict[str, Any] | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class RunStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    node: str
    tool_name: str | None
    input: Any
    output: Any
    error: str | None
    duration_ms: int
    created_at: datetime


# --- LLM structured outputs. Field descriptions are part of the prompt: the model sees them. ---


class Classification(BaseModel):
    """How to handle an operations question."""

    category: Literal["investigate", "knowledge", "out_of_scope"] = Field(
        description=(
            "investigate: about the current or recent behaviour of a service (slow, failing, healthy?, "
            "should we roll back?); needs live monitoring data. "
            "knowledge: how-to or policy questions answerable from runbooks alone. "
            "out_of_scope: anything not about operating our services."
        )
    )
    service: str | None = Field(
        description="Service the question is about, as a lowercase identifier like 'payments'; null if none named"
    )
    window_minutes: int = Field(
        default=30, description="How many minutes of recent data to look at; 30 unless the question says otherwise"
    )


class Diagnosis(BaseModel):
    """Investigation result, grounded in the provided evidence."""

    answer: str = Field(description="Answer to the user's question in Markdown, citing numbers and times")
    likely_cause: str = Field(description="The most likely cause in one sentence, or 'unknown'")
    confidence: Literal["low", "medium", "high"]
    evidence: list[str] = Field(description="Specific observations from the evidence that support the cause")
    recommended_actions: list[str] = Field(
        description="What to do next, following the runbooks; say when an action needs approval"
    )


# --- Evidence gathered for an investigation ---


class Evidence(BaseModel):
    service: str
    window_minutes: int
    metrics: dict[MetricName, MetricSeries] = {}
    error_logs: list[LogEntry] = []
    slow_traces: list[TraceSummary] = []
    deployment: DeploymentState | None = None
    incidents: list[IncidentRead] = []
    # Source name -> why it couldn't be fetched; the diagnosis must account for missing evidence.
    unavailable: dict[str, str] = {}
