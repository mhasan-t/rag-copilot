from src.core.http import request_json
from src.modules.deployments.schemas import DeploymentState


class DemoDeploymentAdapter:
    """Talks to the demo payments service's admin API (DEPLOYMENT_BACKEND=demo)."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    async def get_deployment(self, name: str) -> DeploymentState:
        body = await request_json("GET", f"{self._base_url}/admin/deployments/{name}", upstream="deployment backend")
        return DeploymentState.model_validate(body)
