import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class RemediationProposal(Base):
    """An action the copilot proposed for a run; it only happens after an approval."""

    __tablename__ = "remediation_proposal"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("copilot_run.id", ondelete="CASCADE"), unique=True, comment="At most one proposal per run"
    )
    service: Mapped[str] = mapped_column(String(63), comment="Target; always the service the run investigated")
    action: Mapped[str] = mapped_column(String(64), comment="Name from the remediation.actions catalog")
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, comment="Validated action arguments, e.g. replicas")
    risk_level: Mapped[str] = mapped_column(String(8), comment="low or high, copied from the catalog")
    rationale: Mapped[str] = mapped_column(Text, comment="The LLM's reason for proposing it")
    status: Mapped[str] = mapped_column(
        String(16),
        comment="proposed -> approved | rejected; approved -> executing -> verified | unverified | failed",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # selectin: loaded with the proposal in the same round trip; lazy loading isn't possible with async sessions.
    approval: Mapped[Approval | None] = relationship(lazy="selectin")
    execution: Mapped[ActionExecution | None] = relationship(lazy="selectin")


class Approval(Base):
    """The human decision on a proposal."""

    __tablename__ = "approval"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("remediation_proposal.id", ondelete="CASCADE"), unique=True, comment="One decision per proposal"
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), comment="Who decided")
    decision: Mapped[str] = mapped_column(String(8), comment="approved or rejected")
    comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActionExecution(Base):
    """What happened when an approved proposal was carried out, and whether the service recovered."""

    __tablename__ = "action_execution"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("remediation_proposal.id", ondelete="CASCADE"), unique=True, comment="Executed at most once"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, comment="Deployment state after the action")
    error: Mapped[str | None] = mapped_column(Text, comment="Why the action itself failed")
    verification: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, comment="Metric checks after the action: thresholds, observed values, pass/fail"
    )
