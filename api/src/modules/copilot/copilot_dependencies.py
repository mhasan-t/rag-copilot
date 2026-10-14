from functools import cache
from typing import Annotated

from fastapi import Depends
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from src.core.config import settings
from src.core.llm import build_chat_model
from src.modules.copilot.run_service import CopilotModels
from src.modules.knowledge.knowledge_dependencies import get_embeddings


@cache
def get_chat_model() -> BaseChatModel:
    """One client per process; tests override this dependency with a scripted fake."""
    return build_chat_model()


@cache
def get_classifier_model() -> BaseChatModel:
    """LLM_CLASSIFIER_MODEL if set (a smaller, faster model is enough for routing), else the main model."""
    return build_chat_model(settings.llm_classifier_model) if settings.llm_classifier_model else get_chat_model()


def get_copilot_models(
    chat_model: Annotated[BaseChatModel, Depends(get_chat_model)],
    classifier_model: Annotated[BaseChatModel, Depends(get_classifier_model)],
    embeddings: Annotated[Embeddings, Depends(get_embeddings)],
) -> CopilotModels:
    return CopilotModels(chat_model, classifier_model, embeddings)


def verify_chat_models() -> None:
    """Fails startup if a configured model can't do tool calling, which structured output relies on.

    Only checks the integration's capability; no request is sent, so a model server that is down isn't caught here.
    """
    # Models aren't hashable, so dedupe by identity when the classifier is the main model.
    for model in {id(model): model for model in (get_chat_model(), get_classifier_model())}.values():
        try:
            model.bind_tools([])
        except NotImplementedError as exc:
            raise RuntimeError(
                f"{type(model).__name__} doesn't support tool calling; choose another LLM_PROVIDER/LLM_MODEL"
            ) from exc
