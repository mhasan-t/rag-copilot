import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class CopilotRun(Base):
    """One question asked to the copilot, and its outcome."""

    __tablename__ = "copilot_run"
    __table_args__ = (Index("ix_copilot_run_user_id_created_at", "user_id", text("created_at DESC")),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), comment="Who asked")
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), comment="running, completed or failed")
    classification: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, comment="Category, service and time window the classifier chose"
    )
    answer: Mapped[str | None] = mapped_column(Text, comment="Markdown shown to the user")
    diagnosis: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, comment="Structured cause, confidence and evidence; only for investigations"
    )
    error: Mapped[str | None] = mapped_column(Text, comment="Why the run failed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunStep(Base):
    """Audit trail: one row per graph node, tool call and LLM call of a run."""

    __tablename__ = "run_step"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("copilot_run.id", ondelete="CASCADE"), index=True)
    node: Mapped[str] = mapped_column(String(64), comment="Graph node the step belongs to")
    tool_name: Mapped[str | None] = mapped_column(
        String(64), comment="Tool or LLM call made inside the node; null for the node itself"
    )
    input: Mapped[Any | None] = mapped_column(JSONB, comment="Tool arguments or LLM messages")
    output: Mapped[Any | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer)
    # clock_timestamp(), not now(): parallel steps need distinct, real times for ordering.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
