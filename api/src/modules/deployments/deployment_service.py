from src.core.config import settings
from src.core.logging import logger
from src.core.validation import require_service_name
from src.modules.deployments.demo_deployment_adapter import DemoDeploymentAdapter
from src.modules.deployments.schemas import DeploymentState


class DeploymentService:
    def __init__(self) -> None:
        # ponytail: only the demo backend exists; the kubernetes adapter is planned and selected by DEPLOYMENT_BACKEND.
        self._adapter = DemoDeploymentAdapter(settings.demo_payments_admin_url or "")

    async def get_deployment(self, service: str) -> DeploymentState:
        """Current version and rollout history; raises NotFoundError for unknown services."""
        state = await self._adapter.get_deployment(require_service_name(service))
        logger.info("deployment queried", extra={"service": service, "version": state.version})
        return state
