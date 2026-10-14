import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.core.config import ActionName, MetricName, RiskLevel

type ProposalStatus = Literal["proposed", "approved", "rejected", "executing", "verified", "unverified", "failed"]
type Decision = Literal["approved", "rejected"]


class ProposedAction(BaseModel):
    """An action the LLM suggests. Field descriptions are shown to the model."""

    action: ActionName
    replicas: int | None = Field(default=None, description="Target replica count; only for scale_deployment")
    rationale: str = Field(description="Why this action, citing the evidence and the runbook")


class DecisionRequest(BaseModel):
    comment: Annotated[str | None, Field(max_length=2000)] = None


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    approver_id: uuid.UUID
    decision: Decision
    comment: str | None
    decided_at: datetime


class MetricCheck(BaseModel):
    metric: MetricName
    threshold: float
    value: float | None = Field(description="Latest value; null when there was no data")
    passed: bool


class Verification(BaseModel):
    passed: bool
    checks: list[MetricCheck]
    waited_seconds: int


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    started_at: datetime
    finished_at: datetime | None
    result: dict[str, Any] | None
    error: str | None
    verification: Verification | None


class RemediationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    service: str
    action: ActionName
    params: dict[str, Any]
    risk_level: RiskLevel
    rationale: str
    status: ProposalStatus
    created_at: datetime
    approval: ApprovalRead | None = None
    execution: ExecutionRead | None = None
