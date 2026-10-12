import uuid
from datetime import UTC, datetime

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError, NotFoundError
from src.core.logging import logger
from src.modules.auth.schemas import UserRead
from src.modules.copilot.copilot_graph import CopilotGraph
from src.modules.copilot.copilot_llm import CopilotLLM
from src.modules.copilot.models import CopilotRun
from src.modules.copilot.run_policy import RunPolicy
from src.modules.copilot.run_query import RunQuery
from src.modules.copilot.run_repository import RunRepository
from src.modules.copilot.run_step_service import RunStepService
from src.modules.copilot.schemas import RunRead, RunStepRead


class RunService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._query = RunQuery(session)
        self._repository = RunRepository(session)

    async def ask(
        self,
        actor: UserRead,
        question: str,
        chat_model: BaseChatModel,
        classifier_model: BaseChatModel,
        embeddings: Embeddings,
    ) -> RunRead:
        """Runs the copilot synchronously; the run and its steps are persisted whether it succeeds or fails."""
        run = await self._repository.create_run(user_id=actor.id, question=question, status="running")
        await self._session.commit()
        logger.info("copilot run started", extra={"run_id": run.id, "user_id": actor.id})

        steps = RunStepService(run.id)
        graph = CopilotGraph(CopilotLLM(chat_model, classifier_model, steps), embeddings, steps)
        # BaseException: a cancelled request (client disconnect) must not leave the run "running" forever.
        try:
            state = await graph.run(question)
        except BaseException as exc:
            error = exc.message if isinstance(exc, AppError) else "Internal error"
            await self._finish(run, status="failed", error=error)
            if isinstance(exc, AppError):
                exc.details = {**(exc.details or {}), "run_id": str(run.id)}
            raise

        diagnosis = state.get("diagnosis")
        await self._finish(
            run,
            status="completed",
            classification=state["classification"].model_dump(),
            answer=state["answer"],
            diagnosis=diagnosis.model_dump() if diagnosis else None,
        )
        return RunRead.model_validate(run)

    async def get(self, actor: UserRead, run_id: uuid.UUID) -> RunRead:
        return RunRead.model_validate(await self._get_visible(actor, run_id))

    async def list(self, actor: UserRead, limit: int, offset: int) -> list[RunRead]:
        user_id = None if RunPolicy(actor).can_view_all() else actor.id
        return [RunRead.model_validate(run) for run in await self._query.list(user_id, limit, offset)]

    async def list_steps(self, actor: UserRead, run_id: uuid.UUID) -> list[RunStepRead]:
        run = await self._get_visible(actor, run_id)
        return [RunStepRead.model_validate(step) for step in await self._query.list_steps(run.id)]

    async def _get_visible(self, actor: UserRead, run_id: uuid.UUID) -> CopilotRun:
        run = await self._query.get(run_id)
        # Someone else's run is reported as missing, so run ids can't be probed.
        if run is None or not RunPolicy(actor).can_view(run):
            raise NotFoundError("Run not found", details={"run_id": run_id})
        return run

    async def _finish(self, run: CopilotRun, **values: object) -> None:
        await self._repository.update_run(run, completed_at=datetime.now(UTC), **values)
        await self._session.commit()
        logger.info("copilot run finished", extra={"run_id": run.id, "status": run.status})
