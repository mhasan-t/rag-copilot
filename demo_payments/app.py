"""Dev-only stand-in for a real payments service: gives the copilot telemetry to diagnose and a deployment to roll back.

Telemetry comes from OpenTelemetry auto-instrumentation (`opentelemetry-instrument`), so there is no OTel code here.
Each "version" changes how the service behaves; deploying v2 produces a latency spike and errors.
"""

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

SERVICE_NAME = "payments"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(SERVICE_NAME)


@dataclass(frozen=True)
class VersionProfile:
    latency_seconds: tuple[float, float]
    error_rate: float
    error_message: str


VERSIONS = {
    "v1": VersionProfile((0.02, 0.08), 0.005, "card network declined request: issuer unavailable"),
    # Simulates a bad release: a new ledger query that exhausts the DB connection pool under load.
    "v2": VersionProfile((0.6, 1.8), 0.08, "ledger-db query timed out: connection pool exhausted (size=10)"),
}


class Revision(BaseModel):
    revision: int
    version: str
    deployed_at: datetime


class Deployment(BaseModel):
    name: str
    version: str
    replicas: int
    history: list[Revision]


class DeployRequest(BaseModel):
    version: str


class ScaleRequest(BaseModel):
    replicas: int = Field(ge=1, le=20)


# In-memory on purpose: restarting the container is a "fresh install" of v1.
_history = [Revision(revision=1, version="v1", deployed_at=datetime.now(UTC))]
_replicas = 1

app = FastAPI(title="Demo payments service")


@app.post("/payments", status_code=201)
async def create_payment() -> dict:
    profile = VERSIONS[_history[-1].version]
    await asyncio.sleep(random.uniform(*profile.latency_seconds))
    if random.random() < profile.error_rate:
        logger.error(profile.error_message)
        raise HTTPException(status_code=502, detail="Payment could not be processed")
    payment_id = str(uuid.uuid4())
    logger.info("payment authorized", extra={"payment_id": payment_id})
    return {"id": payment_id, "status": "authorized"}


@app.get("/payments/{payment_id}")
async def get_payment(payment_id: str) -> dict:
    await asyncio.sleep(random.uniform(0.005, 0.02))
    return {"id": payment_id, "status": "authorized"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/admin/deployments/{name}")
async def get_deployment(name: str) -> Deployment:
    _require_known(name)
    return _current()


@app.post("/admin/deployments/{name}/deploy")
async def deploy(name: str, request: DeployRequest) -> Deployment:
    _require_known(name)
    if request.version not in VERSIONS:
        raise HTTPException(status_code=422, detail=f"Unknown version; choose one of {sorted(VERSIONS)}")
    return _roll_out(request.version)


@app.post("/admin/deployments/{name}/rollback")
async def rollback(name: str) -> Deployment:
    """Like `kubectl rollout undo`: re-deploys the previous revision's version as a new revision."""
    _require_known(name)
    if len(_history) < 2:
        raise HTTPException(status_code=409, detail="No previous revision to roll back to")
    return _roll_out(_history[-2].version)


@app.post("/admin/deployments/{name}/restart")
async def restart(name: str) -> Deployment:
    """Like `kubectl rollout restart`: instances restart, version and revision stay the same."""
    _require_known(name)
    logger.warning("deployment restarted", extra={"version": _history[-1].version})
    return _current()


@app.post("/admin/deployments/{name}/scale")
async def scale(name: str, request: ScaleRequest) -> Deployment:
    """Records the replica count only; the demo always runs one process."""
    global _replicas
    _require_known(name)
    _replicas = request.replicas
    logger.warning("deployment scaled", extra={"replicas": _replicas})
    return _current()


def _roll_out(version: str) -> Deployment:
    _history.append(Revision(revision=_history[-1].revision + 1, version=version, deployed_at=datetime.now(UTC)))
    logger.warning("deployment rolled out", extra={"version": version, "revision": _history[-1].revision})
    return _current()


def _current() -> Deployment:
    return Deployment(
        name=SERVICE_NAME, version=_history[-1].version, replicas=_replicas, history=list(reversed(_history))
    )


def _require_known(name: str) -> None:
    if name != SERVICE_NAME:
        raise HTTPException(status_code=404, detail="Deployment not found")
