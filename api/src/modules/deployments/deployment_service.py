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

    # The actions below change production. Callers must have checked approval first (RemediationService does).

    async def rollback(self, service: str) -> DeploymentState:
        """Re-deploys the previous revision's version as a new revision; UpstreamError if there is none."""
        state = await self._adapter.rollback(require_service_name(service))
        logger.warning("deployment rolled back", extra={"service": service, "version": state.version})
        return state

    async def restart(self, service: str) -> DeploymentState:
        state = await self._adapter.restart(require_service_name(service))
        logger.warning("deployment restarted", extra={"service": service})
        return state

    async def scale(self, service: str, replicas: int) -> DeploymentState:
        state = await self._adapter.scale(require_service_name(service), replicas)
        logger.warning("deployment scaled", extra={"service": service, "replicas": replicas})
        return state
