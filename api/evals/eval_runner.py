import time
import uuid

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from evals.fixtures import no_live_backends, replay_backends
from evals.scoring import EvalCase, score
from src.core.database import session_factory
from src.core.exceptions import AppError
from src.modules.auth.schemas import UserRead
from src.modules.copilot.run_service import CopilotModels, RunService
from src.modules.copilot.schemas import RunRead


class CaseResult(BaseModel):
    id: str
    passed: bool
    failures: list[str]
    seconds: float
    run_id: uuid.UUID
    classification: dict | None
    action: str | None
    answer: str | None


async def evaluate(
    cases: list[EvalCase],
    actor: UserRead,
    chat_model: BaseChatModel,
    classifier_model: BaseChatModel,
    embeddings: Embeddings,
) -> list[CaseResult]:
    """Asks each case's question as `actor` and scores the run. Cases run one at a time, as local models prefer.

    Evidence comes only from fixtures: a run can never query the live stack or change a deployment (proposals are
    never approved).
    """
    results = []
    for case in cases:
        backends = replay_backends(case.scenario) if case.scenario else no_live_backends()
        models = CopilotModels(chat_model, classifier_model, embeddings, backends)
        started = time.monotonic()
        async with session_factory() as session:
            run = await _ask(RunService(session), actor, case.question, models)
            steps = await RunService(session).list_steps(actor, run.id)
        failures = score(case, run, steps)
        results.append(
            CaseResult(
                id=case.id,
                passed=not failures,
                failures=failures,
                seconds=round(time.monotonic() - started, 1),
                run_id=run.id,
                classification=run.classification,
                action=run.remediation.action if run.remediation else None,
                answer=run.answer,
            )
        )
    return results


async def _ask(service: RunService, actor: UserRead, question: str, models: CopilotModels) -> RunRead:
    try:
        return await service.ask(actor, question, models)
    except AppError as exc:
        # The run is stored as failed; scoring reports its error. Anything else is a bug and stops the eval.
        run_id = (exc.details or {}).get("run_id")
        if run_id is None:
            raise
        return await service.get(actor, uuid.UUID(run_id))
