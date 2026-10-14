"""The copilot's LangGraph workflow.

classify ─┬─ investigate (service known) ─┬─ retrieve_runbooks ─┬─ diagnose ── propose_remediation ──┐
          │                               └─ gather_evidence ───┘                                    │
          ├─ investigate (no service) ── ask_for_service                       no proposal ── END ◄──┤
          ├─ knowledge ── retrieve_documents ── answer_knowledge                                     │
          └─ out_of_scope ── decline                                                                 ▼
                         await_approval (pauses the run until a human decides) ── rejected ── END
                              │ approved
                         execute_action ── verify_outcome ── END

Each run is a LangGraph thread (thread_id = run id) checkpointed in Postgres, so a paused run can be resumed by a
later request, even after a restart.
"""

import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

from langchain_core.embeddings import Embeddings
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.core.database import session_factory
from src.core.exceptions import InvalidInputError
from src.core.validation import SERVICE_NAME_PATTERN
from src.modules.copilot import prompts
from src.modules.copilot.checkpointer import get_checkpointer
from src.modules.copilot.copilot_llm import CopilotLLM
from src.modules.copilot.evidence_service import EvidenceBackends, EvidenceService
from src.modules.copilot.run_step_service import RunStepService
from src.modules.copilot.schemas import Classification, Diagnosis, Evidence
from src.modules.knowledge.knowledge_service import KnowledgeService
from src.modules.knowledge.schemas import SearchHit
from src.modules.remediation.remediation_service import RemediationService
from src.modules.remediation.schemas import Decision, RemediationRead

MIN_WINDOW_MINUTES, MAX_WINDOW_MINUTES = 5, 24 * 60

type Node = Callable[[CopilotState], Awaitable[dict[str, Any]]]


class CopilotState(TypedDict, total=False):
    question: str
    classification: Classification
    documents: list[SearchHit]
    evidence: Evidence
    diagnosis: Diagnosis
    answer: str
    remediation: RemediationRead
    rejected_proposal: str  # why the LLM's proposed action was invalid and dropped
    decision: Decision


# Every model stored in the state; checkpoints refuse to deserialize any other class.
STATE_TYPES = (Classification, SearchHit, Evidence, Diagnosis, RemediationRead)


class CopilotGraph:
    def __init__(
        self,
        run_id: uuid.UUID,
        llm: CopilotLLM,
        embeddings: Embeddings,
        steps: RunStepService,
        evidence_backends: EvidenceBackends | None = None,
    ):
        self._config = {"configurable": {"thread_id": str(run_id)}}
        self._run_id = run_id
        self._llm = llm
        self._embeddings = embeddings
        self._steps = steps
        self._evidence = EvidenceService(steps, evidence_backends)

    async def run(self, question: str) -> dict[str, Any]:
        """Runs until the end or until it pauses for approval (then the result has an "__interrupt__" key)."""
        return await (await self._compile()).ainvoke({"question": question}, self._config)

    async def resume(self, decision: Decision) -> dict[str, Any]:
        """Continues a run paused at await_approval with the human's decision."""
        return await (await self._compile()).ainvoke(Command(resume=decision), self._config)

    async def _compile(self) -> Any:
        graph = StateGraph(CopilotState)
        nodes: dict[str, Node] = {
            "classify": self._classify,
            "retrieve_runbooks": self._retrieve,
            "gather_evidence": self._gather_evidence,
            "diagnose": self._diagnose,
            "propose_remediation": self._propose_remediation,
            "execute_action": self._execute_action,
            "verify_outcome": self._verify_outcome,
            "retrieve_documents": self._retrieve,
            "answer_knowledge": self._answer_knowledge,
            "ask_for_service": self._fixed_answer(prompts.NEEDS_SERVICE_ANSWER),
            "decline": self._fixed_answer(prompts.OUT_OF_SCOPE_ANSWER),
        }
        for name, node in nodes.items():
            graph.add_node(name, self._traced(name, node))
        # Not wrapped by _traced: it raises to pause, and records its own step once a decision arrives.
        graph.add_node("await_approval", self._await_approval)

        graph.add_edge(START, "classify")
        graph.add_conditional_edges(
            "classify",
            _route_question,
            ["retrieve_runbooks", "gather_evidence", "retrieve_documents", "ask_for_service", "decline"],
        )
        # A join: diagnose runs once both parallel branches have finished.
        graph.add_edge(["retrieve_runbooks", "gather_evidence"], "diagnose")
        graph.add_edge("diagnose", "propose_remediation")
        graph.add_conditional_edges("propose_remediation", _route_after_proposal, ["await_approval", END])
        graph.add_conditional_edges("await_approval", _route_after_decision, ["execute_action", END])
        graph.add_conditional_edges("execute_action", _route_after_execution, ["verify_outcome", END])
        graph.add_edge("retrieve_documents", "answer_knowledge")
        for terminal in ("verify_outcome", "answer_knowledge", "ask_for_service", "decline"):
            graph.add_edge(terminal, END)
        return graph.compile(checkpointer=await get_checkpointer(STATE_TYPES))

    async def _classify(self, state: CopilotState) -> dict[str, Any]:
        classification = await self._llm.classify(state["question"])
        # The LLM's output is untrusted input: clamp the window and drop service names that aren't identifiers.
        classification.window_minutes = min(max(classification.window_minutes, MIN_WINDOW_MINUTES), MAX_WINDOW_MINUTES)
        service = (classification.service or "").strip().lower()
        classification.service = service if re.fullmatch(SERVICE_NAME_PATTERN, service) else None
        return {"classification": classification}

    async def _retrieve(self, state: CopilotState) -> dict[str, Any]:
        async with session_factory() as session:
            hits = await KnowledgeService(session, self._embeddings).search(
                state["question"], state["classification"].service
            )
        return {"documents": hits}

    async def _gather_evidence(self, state: CopilotState) -> dict[str, Any]:
        classification = state["classification"]
        if classification.service is None:
            raise RuntimeError("gather_evidence needs a service; _route_question should have prevented this")
        return {"evidence": await self._evidence.gather(classification.service, classification.window_minutes)}

    async def _diagnose(self, state: CopilotState) -> dict[str, Any]:
        diagnosis = await self._llm.diagnose(state["question"], state["documents"], state["evidence"])
        return {"diagnosis": diagnosis, "answer": diagnosis.answer}

    async def _propose_remediation(self, state: CopilotState) -> dict[str, Any]:
        proposed = state["diagnosis"].proposed_action
        if proposed is None:
            return {}
        service = state["evidence"].service  # never the LLM's choice: only the service that was investigated
        async with session_factory() as session:
            try:
                return {"remediation": await RemediationService(session).propose(self._run_id, service, proposed)}
            except InvalidInputError as exc:
                # An invalid proposal (e.g. 50 replicas) is dropped, not adjusted into something else.
                return {"rejected_proposal": exc.message}

    async def _await_approval(self, state: CopilotState) -> dict[str, Any]:
        # Pauses the run here. On resume LangGraph runs this node again, and interrupt() returns the decision.
        decision: Decision = interrupt({"proposal_id": str(state["remediation"].id)})
        async with self._steps.track("await_approval") as step:
            step.output = {"decision": decision}
        return {"decision": decision}

    async def _execute_action(self, state: CopilotState) -> dict[str, Any]:
        async with session_factory() as session:
            return {"remediation": await RemediationService(session).execute(state["remediation"].id)}

    async def _verify_outcome(self, state: CopilotState) -> dict[str, Any]:
        async with session_factory() as session:
            return {"remediation": await RemediationService(session).verify(state["remediation"].id)}

    async def _answer_knowledge(self, state: CopilotState) -> dict[str, Any]:
        return {"answer": await self._llm.answer_from_documents(state["question"], state["documents"])}

    @staticmethod
    def _fixed_answer(answer: str) -> Node:
        async def node(_: CopilotState) -> dict[str, Any]:
            return {"answer": answer}

        return node

    def _traced(self, name: str, node: Node) -> Node:
        """Records each node's result as a step; tool and LLM calls inside it record their own steps."""

        async def traced(state: CopilotState) -> dict[str, Any]:
            async with self._steps.track(name) as step:
                update = await node(state)
                step.output = update
            return update

        return traced


def _route_question(state: CopilotState) -> str | list[str]:
    classification = state["classification"]
    if classification.category == "out_of_scope":
        return "decline"
    if classification.category == "knowledge":
        return "retrieve_documents"
    if classification.service is None:
        return "ask_for_service"
    return ["retrieve_runbooks", "gather_evidence"]


def _route_after_proposal(state: CopilotState) -> Literal["await_approval", "__end__"]:
    return "await_approval" if "remediation" in state else END


def _route_after_decision(state: CopilotState) -> Literal["execute_action", "__end__"]:
    return "execute_action" if state["decision"] == "approved" else END


def _route_after_execution(state: CopilotState) -> Literal["verify_outcome", "__end__"]:
    return "verify_outcome" if state["remediation"].status == "executing" else END
