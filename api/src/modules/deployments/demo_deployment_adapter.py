from typing import Any

from src.core.http import request_json
from src.modules.deployments.schemas import DeploymentState


class DemoDeploymentAdapter:
    """Talks to the demo payments service's admin API (DEPLOYMENT_BACKEND=demo)."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def get_deployment(self, name: str) -> DeploymentState:
        return await self._call("GET", name, "")

    async def rollback(self, name: str) -> DeploymentState:
        return await self._call("POST", name, "/rollback")

    async def restart(self, name: str) -> DeploymentState:
        return await self._call("POST", name, "/restart")

    async def scale(self, name: str, replicas: int) -> DeploymentState:
        return await self._call("POST", name, "/scale", json={"replicas": replicas})

    async def _call(self, method: str, name: str, action: str, **kwargs: Any) -> DeploymentState:
        url = f"{self._base_url}/admin/deployments/{name}{action}"
        return DeploymentState.model_validate(await request_json(method, url, upstream="deployment backend", **kwargs))
