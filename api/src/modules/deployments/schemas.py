from datetime import datetime

from pydantic import BaseModel


class DeploymentRevision(BaseModel):
    revision: int
    version: str
    deployed_at: datetime


class DeploymentState(BaseModel):
    name: str
    version: str
    replicas: int
    history: list[DeploymentRevision]  # newest first
