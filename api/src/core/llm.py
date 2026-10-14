from typing import Any

from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from src.core.config import settings


def _connection_kwargs(base_url: str | None, api_key: SecretStr | None) -> dict[str, Any]:
    """Only pass what is set, so providers fall back to their own defaults and native env vars."""
    kwargs: dict[str, Any] = {}
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key.get_secret_value()
    return kwargs


def build_chat_model(model: str | None = None, provider: str | None = None) -> BaseChatModel:
    """Chat model for the configured provider; `model` and `provider` override LLM_MODEL and LLM_PROVIDER.

    With a different provider, LLM_BASE_URL and LLM_API_KEY don't apply; the provider's SDK reads its own
    environment variables (e.g. OPENAI_API_KEY) instead.
    """
    same_provider = provider in (None, settings.llm_provider)
    connection = _connection_kwargs(settings.llm_base_url, settings.llm_api_key) if same_provider else {}
    return init_chat_model(
        model or settings.llm_model, model_provider=provider or settings.llm_provider, temperature=0, **connection
    )


def build_embeddings() -> Embeddings:
    return init_embeddings(
        settings.embedding_model,
        provider=settings.embedding_provider,
        **_connection_kwargs(settings.embedding_base_url, settings.embedding_api_key),
    )
