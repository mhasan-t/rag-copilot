import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from opentelemetry import metrics, trace
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import background
from src.core.database import session_factory
from src.core.exceptions import AppError, NotFoundError
from src.core.logging import logger
from src.modules.auth.schemas import UserRead
from src.modules.copilot.copilot_graph import CopilotGraph
from src.modules.copilot.copilot_llm import CopilotLLM
from src.modules.copilot.evidence_service import EvidenceBackends
from src.modules.copilot.models import CopilotRun
from src.modules.copilot.run_policy import RunPolicy
from src.modules.copilot.run_query import RunQuery
from src.modules.copilot.run_repository import RunRepository
from src.modules.copilot.run_step_service import RunStepService
from src.modules.copilot.schemas import RunRead, RunStepRead
from src.modules.remediation.remediation_query import RemediationQuery
from src.modules.remediation.remediation_service import RemediationService
from src.modules.remediation.schemas import Decision, RemediationRead

_tracer = trace.get_tracer(__name__)
_runs = metrics.get_meter(__name__).create_counter(
    "copilot.runs", unit="{run}", description="Copilot runs reaching a status other than running"
)


class CopilotModels:
    """The models a graph needs; passed through from the request's dependencies.

    `evidence_backends` defaults to the live monitoring and deployment services; the evals replay fixtures instead.
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        classifier_model: BaseChatModel,
        embeddings: Embeddings,
        evidence_backends: EvidenceBackends | None = None,
    ):
        self.chat_model = chat_model
        self.classifier_model = classifier_model
        self.embeddings = embeddings
        self.evidence_backends = evidence_backends

    def graph(self, run_id: uuid.UUID) -> CopilotGraph:
        steps = RunStepService(run_id)
        llm = CopilotLLM(self.chat_model, self.classifier_model, steps)
        return CopilotGraph(run_id, llm, self.embeddings, steps, self.evidence_backends)


class RunService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._query = RunQuery(session)
        self._repository = RunRepository(session)

    async def ask(self, actor: UserRead, question: str, models: CopilotModels) -> RunRead:
        """Runs the copilot until it answers or pauses for approval; persisted whether it succeeds or fails."""
        run = await self._repository.create_run(user_id=actor.id, question=question, status="running")
        await self._session.commit()
        logger.info("copilot run started", extra={"run_id": run.id, "user_id": actor.id})
        with _tracer.start_as_current_span("copilot.run", attributes={"copilot.run_id": str(run.id)}):
            await self._advance(run, lambda: models.graph(run.id).run(question))
        return await self._read(run)

    async def decide_remediation(
        self, actor: UserRead, proposal_id: uuid.UUID, decision: Decision, comment: str | None, models: CopilotModels
    ) -> RemediationRead:
        """Records the decision, then resumes the paused run.

        After an approval the action and its verification (which can take minutes) continue in the background;
        poll the run or the remediation for the outcome. A rejection finishes the run before returning.
        """
        proposal = await RemediationService(self._session).decide(actor, proposal_id, decision, comment)
        resume = self.resume_in_new_session(proposal.run_id, decision, models)
        if decision == "approved":
            background.spawn(resume, name=f"resume-run-{proposal.run_id}")
        else:
            await resume
        return proposal

    @classmethod
    async def resume_in_new_session(cls, run_id: uuid.UUID, decision: Decision, models: CopilotModels) -> None:
        """Continues a paused run. Uses its own session because it may outlive the request that triggered it."""
        async with session_factory() as session:
            service = cls(session)
            run = await service._query.get(run_id)
            if run is None:
                raise NotFoundError("Run not found", details={"run_id": run_id})
            await service._update(run, status="running")
            attributes = {"copilot.run_id": str(run_id), "copilot.decision": decision}
            with _tracer.start_as_current_span("copilot.resume", attributes=attributes):
                await service._advance(run, lambda: models.graph(run_id).resume(decision))

    async def get(self, actor: UserRead, run_id: uuid.UUID) -> RunRead:
        return await self._read(await self._get_visible(actor, run_id))

    async def list(self, actor: UserRead, limit: int, offset: int) -> list[RunRead]:
        user_id = None if RunPolicy(actor).can_view_all() else actor.id
        return await self._read_many(await self._query.list(user_id, limit, offset))

    async def list_steps(self, actor: UserRead, run_id: uuid.UUID) -> list[RunStepRead]:
        run = await self._get_visible(actor, run_id)
        return [RunStepRead.model_validate(step) for step in await self._query.list_steps(run.id)]

    async def _advance(self, run: CopilotRun, step: Any) -> None:
        """Runs the graph until it pauses or ends and records where the run got to."""
        # BaseException: a cancelled request (client disconnect) must not leave the run "running" forever.
        try:
            state = await step()
        except BaseException as exc:
            error = exc.message if isinstance(exc, AppError) else "Internal error"
            await self._update(run, status="failed", error=error, completed_at=datetime.now(UTC))
            await RemediationService(self._session).abandon(run.id, error)
            if isinstance(exc, AppError):
                exc.details = {**(exc.details or {}), "run_id": str(run.id)}
            raise

        values: dict[str, Any] = {
            "classification": state["classification"].model_dump(),
            "answer": state["answer"],
            "diagnosis": state["diagnosis"].model_dump() if "diagnosis" in state else None,
        }
        if "__interrupt__" in state:
            await self._update(run, status="awaiting_approval", **values)
        else:
            status = "rejected" if state.get("decision") == "rejected" else "completed"
            await self._update(run, status=status, completed_at=datetime.now(UTC), **values)

    async def _get_visible(self, actor: UserRead, run_id: uuid.UUID) -> CopilotRun:
        run = await self._query.get(run_id)
        # Someone else's run is reported as missing, so run ids can't be probed.
        if run is None or not RunPolicy(actor).can_view(run):
            raise NotFoundError("Run not found", details={"run_id": run_id})
        return run

    async def _update(self, run: CopilotRun, **values: Any) -> None:
        await self._repository.update_run(run, **values)
        await self._session.commit()
        logger.info("copilot run updated", extra={"run_id": run.id, "status": run.status})
        if run.status != "running":
            _runs.add(1, {"status": run.status})

    async def _read(self, run: CopilotRun) -> RunRead:
        [read] = await self._read_many([run])
        return read

    async def _read_many(self, runs: Sequence[CopilotRun]) -> list[RunRead]:
        proposals = await RemediationQuery(self._session).list_for_runs([run.id for run in runs])
        by_run = {proposal.run_id: RemediationRead.model_validate(proposal) for proposal in proposals}
        return [RunRead.model_validate(run).model_copy(update={"remediation": by_run.get(run.id)}) for run in runs]
