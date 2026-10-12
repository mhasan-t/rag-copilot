"""The copilot's LangGraph workflow (read-only: it investigates and recommends, it doesn't act).

classify ─┬─ investigate (service known) ─┬─ retrieve_runbooks ─┬─ diagnose
          │                               └─ gather_evidence ───┘
          ├─ investigate (no service) ── ask_for_service
          ├─ knowledge ── retrieve_documents ── answer_knowledge
          └─ out_of_scope ── decline
"""

import re
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langchain_core.embeddings import Embeddings
from langgraph.graph import END, START, StateGraph

from src.core.database import session_factory
from src.core.validation import SERVICE_NAME_PATTERN
from src.modules.copilot import prompts
from src.modules.copilot.copilot_llm import CopilotLLM
from src.modules.copilot.evidence_service import EvidenceService
from src.modules.copilot.run_step_service import RunStepService
from src.modules.copilot.schemas import Classification, Diagnosis, Evidence
from src.modules.knowledge.knowledge_service import KnowledgeService
from src.modules.knowledge.schemas import SearchHit

MIN_WINDOW_MINUTES, MAX_WINDOW_MINUTES = 5, 24 * 60

type Node = Callable[[CopilotState], Awaitable[dict[str, Any]]]


class CopilotState(TypedDict, total=False):
    question: str
    classification: Classification
    documents: list[SearchHit]
    evidence: Evidence
    diagnosis: Diagnosis
    answer: str


class CopilotGraph:
    def __init__(self, llm: CopilotLLM, embeddings: Embeddings, steps: RunStepService):
        self._llm = llm
        self._embeddings = embeddings
        self._steps = steps
        self._evidence = EvidenceService(steps)
        self._graph = self._build()

    async def run(self, question: str) -> CopilotState:
        return await self._graph.ainvoke({"question": question})

    def _build(self) -> Any:
        graph = StateGraph(CopilotState)
        nodes: dict[str, Node] = {
            "classify": self._classify,
            "retrieve_runbooks": self._retrieve,
            "gather_evidence": self._gather_evidence,
            "diagnose": self._diagnose,
            "retrieve_documents": self._retrieve,
            "answer_knowledge": self._answer_knowledge,
            "ask_for_service": self._fixed_answer(prompts.NEEDS_SERVICE_ANSWER),
            "decline": self._fixed_answer(prompts.OUT_OF_SCOPE_ANSWER),
        }
        for name, node in nodes.items():
            graph.add_node(name, self._traced(name, node))

        graph.add_edge(START, "classify")
        graph.add_conditional_edges(
            "classify",
            _route,
            ["retrieve_runbooks", "gather_evidence", "retrieve_documents", "ask_for_service", "decline"],
        )
        # A join: diagnose runs once both parallel branches have finished.
        graph.add_edge(["retrieve_runbooks", "gather_evidence"], "diagnose")
        graph.add_edge("retrieve_documents", "answer_knowledge")
        for terminal in ("diagnose", "answer_knowledge", "ask_for_service", "decline"):
            graph.add_edge(terminal, END)
        return graph.compile()

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
            raise RuntimeError("gather_evidence needs a service; _route should have prevented this")
        return {"evidence": await self._evidence.gather(classification.service, classification.window_minutes)}

    async def _diagnose(self, state: CopilotState) -> dict[str, Any]:
        diagnosis = await self._llm.diagnose(state["question"], state["documents"], state["evidence"])
        return {"diagnosis": diagnosis, "answer": diagnosis.answer}

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


def _route(state: CopilotState) -> str | list[str]:
    classification = state["classification"]
    if classification.category == "out_of_scope":
        return "decline"
    if classification.category == "knowledge":
        return "retrieve_documents"
    if classification.service is None:
        return "ask_for_service"
    return ["retrieve_runbooks", "gather_evidence"]
