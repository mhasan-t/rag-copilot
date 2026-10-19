import asyncio
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from opentelemetry import metrics, trace
from pydantic import BaseModel

from src.core.config import app_config
from src.core.exceptions import UpstreamError
from src.modules.copilot import prompts
from src.modules.copilot.run_step_service import RunStepService
from src.modules.copilot.schemas import Classification, Diagnosis, Evidence
from src.modules.knowledge.schemas import SearchHit

_tokens = metrics.get_meter(__name__).create_counter(
    "copilot.llm.tokens", unit="{token}", description="Tokens sent to and received from the LLM"
)


class CopilotLLM:
    """Every LLM call the copilot makes; each one is time-limited and recorded as a step with its exact prompt."""

    def __init__(self, chat_model: BaseChatModel, classifier_model: BaseChatModel, steps: RunStepService):
        self._chat_model = chat_model
        self._classifier_model = classifier_model
        self._steps = steps

    async def classify(self, question: str) -> Classification:
        messages = prompts.CLASSIFY_PROMPT.format_messages(question=question)
        return await self._structured("classify", self._classifier_model, Classification, messages)

    async def diagnose(self, question: str, documents: list[SearchHit], evidence: Evidence) -> Diagnosis:
        messages = prompts.DIAGNOSE_PROMPT.format_messages(
            documents=prompts.render_documents(documents), evidence=prompts.render_evidence(evidence), question=question
        )
        return await self._structured("diagnose", self._chat_model, Diagnosis, messages)

    async def answer_from_documents(self, question: str, documents: list[SearchHit]) -> str:
        messages = prompts.KNOWLEDGE_PROMPT.format_messages(
            documents=prompts.render_documents(documents), question=question
        )
        async with self._steps.track("answer_knowledge", tool_name="llm", input=_loggable(messages)) as step:
            response = await self._call(self._chat_model.ainvoke(messages))
            _record_usage("answer_knowledge", self._chat_model, response)
            step.output = response.content
        return str(response.content)

    async def _structured[T: BaseModel](
        self, node: str, model: BaseChatModel, schema: type[T], messages: list[BaseMessage]
    ) -> T:
        async with self._steps.track(node, tool_name="llm", input=_loggable(messages)) as step:
            # include_raw keeps the model's actual reply, which is where token usage is reported.
            response = await self._call(model.with_structured_output(schema, include_raw=True).ainvoke(messages))
            _record_usage(node, model, response["raw"])
            result = response["parsed"]
            if result is None:
                raise UpstreamError(
                    f"LLM reply didn't match the {schema.__name__} schema",
                    details={"error": str(response["parsing_error"] or "no structured output")[:300]},
                )
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


def _record_usage(node: str, model: BaseChatModel, response: AIMessage) -> None:
    """Token counts on the step's span (GenAI semantic conventions) and in the token counter, when reported."""
    model_name = getattr(model, "model_name", None) or getattr(model, "model", None) or type(model).__name__
    span = trace.get_current_span()
    span.set_attribute("gen_ai.request.model", str(model_name))
    usage = response.usage_metadata
    if usage is None:  # not every provider reports usage
        return
    for token_type, count in (("input", usage["input_tokens"]), ("output", usage["output_tokens"])):
        span.set_attribute(f"gen_ai.usage.{token_type}_tokens", count)
        _tokens.add(count, {"node": node, "type": token_type, "model": str(model_name)})
