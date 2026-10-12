import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class Incident(Base):
    __tablename__ = "incident"
    # "Recent incidents for a service" is the only access pattern.
    __table_args__ = (Index("ix_incident_service_started_at", "service", text("started_at DESC")),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    service: Mapped[str] = mapped_column(String(63), comment="Affected service, same name as in monitoring")
    severity: Mapped[str] = mapped_column(String(8), comment="sev1 (worst) to sev4")
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, comment="What happened, the cause and how it was resolved")
    status: Mapped[str] = mapped_column(String(16), comment="open or resolved")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
