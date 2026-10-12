import asyncio
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from src.core.config import app_config
from src.core.exceptions import UpstreamError
from src.modules.copilot import prompts
from src.modules.copilot.run_step_service import RunStepService
from src.modules.copilot.schemas import Classification, Diagnosis, Evidence
from src.modules.knowledge.schemas import SearchHit


class CopilotLLM:
    """Every LLM call the copilot makes; each one is time-limited and recorded as a step with its exact prompt."""

    def __init__(self, chat_model: BaseChatModel, classifier_model: BaseChatModel, steps: RunStepService):
        self._chat_model = chat_model
        self._classifier_model = classifier_model
        self._steps = steps

    async def classify(self, question: str) -> Classification:
        messages = [SystemMessage(prompts.CLASSIFY_SYSTEM), HumanMessage(question)]
        return await self._structured("classify", self._classifier_model, Classification, messages)

    async def diagnose(self, question: str, documents: list[SearchHit], evidence: Evidence) -> Diagnosis:
        context = f"{prompts.render_documents(documents)}\n\n{prompts.render_evidence(evidence)}"
        messages = [SystemMessage(prompts.DIAGNOSE_SYSTEM), HumanMessage(f"{context}\n\nQuestion: {question}")]
        return await self._structured("diagnose", self._chat_model, Diagnosis, messages)

    async def answer_from_documents(self, question: str, documents: list[SearchHit]) -> str:
        messages = [
            SystemMessage(prompts.KNOWLEDGE_SYSTEM),
            HumanMessage(f"{prompts.render_documents(documents)}\n\nQuestion: {question}"),
        ]
        async with self._steps.track("answer_knowledge", tool_name="llm", input=_loggable(messages)) as step:
            response = await self._call(self._chat_model.ainvoke(messages))
            step.output = response.content
        return str(response.content)

    async def _structured[T: BaseModel](
        self, node: str, model: BaseChatModel, schema: type[T], messages: list[BaseMessage]
    ) -> T:
        async with self._steps.track(node, tool_name="llm", input=_loggable(messages)) as step:
            result = await self._call(model.with_structured_output(schema).ainvoke(messages))
            step.output = result
        return result

    @staticmethod
    async def _call(call: Any) -> Any:
        # Providers raise their own exception types; to callers they all mean "the model is unavailable".
        try:
            async with asyncio.timeout(app_config.copilot.llm_timeout_seconds):
                return await call
        except TimeoutError as exc:
            raise UpstreamError("LLM provider timed out") from exc
        except Exception as exc:
            raise UpstreamError("LLM provider failed", details={"error": type(exc).__name__}) from exc


def _loggable(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    return [{"role": message.type, "content": message.content} for message in messages]
