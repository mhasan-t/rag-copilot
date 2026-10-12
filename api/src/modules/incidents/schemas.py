import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.core.validation import ServiceName


class IncidentCreate(BaseModel):
    service: ServiceName
    severity: Literal["sev1", "sev2", "sev3", "sev4"]
    title: str
    summary: str
    status: Literal["open", "resolved"]
    started_at: datetime
    resolved_at: datetime | None


class IncidentRead(IncidentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
