from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

type Handler = Callable[[str], Any]


class ScriptedChatModel(BaseChatModel):
    """Fake chat model for tests that still goes through LangChain's real tool-calling/structured-output path.

    `handlers` maps a structured-output schema name (e.g. "Diagnosis"), or "text" for plain calls, to a function
    that receives the full prompt text and returns the schema's fields (or the text). Every prompt is kept in
    `prompts` under the same key, so tests can check what the LLM was shown.
    """

    handlers: dict[str, Handler]
    prompts: dict[str, list[str]] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Any:
        return self.bind(tools=[convert_to_openai_tool(tool) for tool in tools], **kwargs)

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any):
        tools = kwargs.get("tools")
        key = tools[0]["function"]["name"] if tools else "text"
        prompt = "\n\n".join(str(message.content) for message in messages)
        self.prompts.setdefault(key, []).append(prompt)
        result = self.handlers[key](prompt)
        # Deterministic stand-in for provider-reported usage: one token per word in, a fixed 10 out.
        usage = {"input_tokens": len(prompt.split()), "output_tokens": 10, "total_tokens": len(prompt.split()) + 10}
        if tools:
            tool_call = {"name": key, "args": result, "id": "call-1"}
            message = AIMessage(content="", tool_calls=[tool_call], usage_metadata=usage)
        else:
            message = AIMessage(content=result, usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=message)])
