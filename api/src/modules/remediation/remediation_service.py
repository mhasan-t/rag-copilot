import asyncio
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import ActionName, RiskLevel, app_config
from src.core.exceptions import AppError, ConflictError, ForbiddenError, InvalidInputError, NotFoundError
from src.core.logging import logger
from src.modules.auth.schemas import UserRead
from src.modules.auth.user_query import UserQuery
from src.modules.deployments.deployment_service import DeploymentService
from src.modules.deployments.schemas import DeploymentState
from src.modules.monitoring.monitoring_service import MonitoringService
from src.modules.remediation.approval_policy import ApprovalPolicy
from src.modules.remediation.models import RemediationProposal
from src.modules.remediation.remediation_query import RemediationQuery
from src.modules.remediation.remediation_repository import RemediationRepository
from src.modules.remediation.schemas import Decision, MetricCheck, ProposedAction, RemediationRead, Verification

# Recent enough to reflect the action, long enough for a stable rate (the queries use a 60 s rate window).
VERIFY_WINDOW_MINUTES = 5


class RemediationService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._query = RemediationQuery(session)
        self._repository = RemediationRepository(session)

    async def propose(self, run_id: uuid.UUID, service: str, proposed: ProposedAction) -> RemediationRead:
        """Validates an LLM-proposed action against the catalog and stores it, awaiting a decision."""
        params: dict[str, int] = {}
        if proposed.action == ActionName.SCALE_DEPLOYMENT:
            max_replicas = app_config.remediation.max_replicas
            if proposed.replicas is None or not 1 <= proposed.replicas <= max_replicas:
                raise InvalidInputError(f"scale_deployment needs replicas between 1 and {max_replicas}")
            params["replicas"] = proposed.replicas

        proposal = await self._repository.create_proposal(
            run_id=run_id,
            service=service,
            action=proposed.action,
            params=params,
            # Risk comes from the catalog, never from the LLM.
            risk_level=app_config.remediation.actions[proposed.action].risk,
            rationale=proposed.rationale,
            status="proposed",
        )
        await self._session.commit()
        logger.info("remediation proposed", extra={"proposal_id": proposal.id, "action": proposal.action})
        return await self._read(proposal.id)

    async def get(self, actor: UserRead, proposal_id: uuid.UUID) -> RemediationRead:
        proposal, owner_id = await self._get_with_owner(proposal_id)
        if not (await self._policy(actor)).can_view(RiskLevel(proposal.risk_level), owner_id):
            raise NotFoundError("Remediation not found", details={"proposal_id": proposal_id})
        return RemediationRead.model_validate(proposal)

    async def list(self, actor: UserRead, status: str | None, limit: int, offset: int) -> list[RemediationRead]:
        visible_to = None if actor.is_superuser else actor.id
        return [RemediationRead.model_validate(p) for p in await self._query.list(status, visible_to, limit, offset)]

    async def decide(
        self, actor: UserRead, proposal_id: uuid.UUID, decision: Decision, comment: str | None
    ) -> RemediationRead:
        proposal, owner_id = await self._get_with_owner(proposal_id)
        policy = await self._policy(actor)
        risk = RiskLevel(proposal.risk_level)
        if not policy.can_view(risk, owner_id):
            raise NotFoundError("Remediation not found", details={"proposal_id": proposal_id})
        allowed = policy.can_approve(risk, owner_id) if decision == "approved" else policy.can_reject(risk, owner_id)
        if not allowed:
            raise ForbiddenError(f"Not allowed to {decision.removesuffix('d')} this {risk} risk action")

        if not await self._repository.transition(proposal_id, "proposed", decision):
            raise ConflictError("This remediation has already been decided")
        await self._repository.add_approval(
            proposal_id=proposal_id, approver_id=actor.id, decision=decision, comment=comment
        )
        await self._session.commit()
        logger.warning(f"remediation {decision}", extra={"proposal_id": proposal_id, "actor_id": actor.id})
        return await self._read(proposal_id)

    async def execute(self, proposal_id: uuid.UUID) -> RemediationRead:
        """Carries out an approved proposal, exactly once. The final gate: the graph alone can't make this happen."""
        if not await self._repository.transition(proposal_id, "approved", "executing"):
            proposal = await self._require(proposal_id)
            if proposal.status in ("proposed", "rejected"):
                raise ForbiddenError("Remediation has not been approved", details={"status": proposal.status})
            raise ConflictError("Remediation has already been executed", details={"status": proposal.status})
        execution = await self._repository.create_execution(proposal_id)
        await self._session.commit()

        proposal = await self._require(proposal_id)
        logger.warning("remediation executing", extra={"proposal_id": proposal_id, "action": proposal.action})
        try:
            state = await self._run_action(proposal)
        except AppError as exc:
            await self._repository.update_execution(execution, error=exc.message, finished_at=datetime.now(UTC))
            await self._repository.transition(proposal_id, "executing", "failed")
            await self._session.commit()
            logger.error("remediation failed", extra={"proposal_id": proposal_id, "error": exc.message})
            return await self._read(proposal_id)

        await self._repository.update_execution(
            execution, result=state.model_dump(mode="json"), finished_at=datetime.now(UTC)
        )
        await self._session.commit()
        return await self._read(proposal_id)

    async def verify(self, proposal_id: uuid.UUID) -> RemediationRead:
        """Polls the service's metrics until every threshold is met or the timeout passes."""
        proposal = await self._require(proposal_id)
        config = app_config.remediation.verification
        started = time.monotonic()
        while True:
            verification = await self._check_metrics(proposal.service, started)
            if verification.passed or time.monotonic() - started >= config.timeout_seconds:
                break
            await asyncio.sleep(config.poll_seconds)

        if proposal.execution is None:
            raise ConflictError("Remediation was never executed")
        await self._repository.update_execution(proposal.execution, verification=verification.model_dump(mode="json"))
        await self._repository.transition(proposal_id, "executing", "verified" if verification.passed else "unverified")
        await self._session.commit()
        logger.info("remediation verified", extra={"proposal_id": proposal_id, "passed": verification.passed})
        return await self._read(proposal_id)

    async def abandon(self, run_id: uuid.UUID, reason: str) -> None:
        """Marks a run's approved or in-progress proposal as failed when the run itself failed.

        Otherwise nothing would ever finish it, and it would look like the action is still under way.
        """
        proposals = await self._query.list_for_runs([run_id])
        if not proposals or proposals[0].status not in ("approved", "executing"):
            return
        proposal = proposals[0]
        await self._repository.transition(proposal.id, proposal.status, "failed")
        if proposal.execution is not None and proposal.execution.finished_at is None:
            await self._repository.update_execution(
                proposal.execution, error=f"Run failed: {reason}", finished_at=datetime.now(UTC)
            )
        await self._session.commit()
        logger.error("remediation abandoned", extra={"proposal_id": proposal.id, "reason": reason})

    async def _check_metrics(self, service: str, started: float) -> Verification:
        monitoring = MonitoringService()
        checks = []
        for metric, threshold in app_config.remediation.verification.thresholds.items():
            try:
                series = await monitoring.get_metric(service, metric, VERIFY_WINDOW_MINUTES)
                value = series.points[-1].value if series.points else None
            except AppError:
                value = None  # unknown counts as not recovered
            passed = value is not None and value <= threshold
            checks.append(MetricCheck(metric=metric, threshold=threshold, value=value, passed=passed))
        return Verification(
            passed=all(check.passed for check in checks),
            checks=checks,
            waited_seconds=round(time.monotonic() - started),
        )

    @staticmethod
    async def _run_action(proposal: RemediationProposal) -> DeploymentState:
        deployments = DeploymentService()
        match ActionName(proposal.action):
            case ActionName.ROLLBACK_DEPLOYMENT:
                return await deployments.rollback(proposal.service)
            case ActionName.RESTART_DEPLOYMENT:
                return await deployments.restart(proposal.service)
            case ActionName.SCALE_DEPLOYMENT:
                return await deployments.scale(proposal.service, proposal.params["replicas"])

    async def _policy(self, actor: UserRead) -> ApprovalPolicy:
        return ApprovalPolicy(actor, await UserQuery(self._session).count_active_superusers())

    async def _get_with_owner(self, proposal_id: uuid.UUID) -> tuple[RemediationProposal, uuid.UUID]:
        row = await self._query.get_with_owner(proposal_id)
        if row is None:
            raise NotFoundError("Remediation not found", details={"proposal_id": proposal_id})
        return row[0], row[1]

    async def _require(self, proposal_id: uuid.UUID) -> RemediationProposal:
        proposal = await self._query.get(proposal_id)
        if proposal is None:
            raise NotFoundError("Remediation not found", details={"proposal_id": proposal_id})
        return proposal

    async def _read(self, proposal_id: uuid.UUID) -> RemediationRead:
        return RemediationRead.model_validate(await self._require(proposal_id))
