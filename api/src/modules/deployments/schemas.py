from datetime import datetime

from pydantic import BaseModel, Field


class DeploymentRevision(BaseModel):
    revision: int
    version: str
    deployed_at: datetime | None = Field(
        description="When this revision went live; null when unknown (a past rollback target in Kubernetes)"
    )


class DeploymentState(BaseModel):
    name: str
    version: str
    replicas: int
    history: list[DeploymentRevision]  # newest first
