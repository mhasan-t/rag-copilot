from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from src.core.config import settings
from src.core.llm import build_chat_model, build_embeddings


def test_factories_build_models_for_the_configured_provider():
    # Construction does not call the provider, so this checks env wiring without network access.
    assert isinstance(build_chat_model(), BaseChatModel)
    assert isinstance(build_embeddings(), Embeddings)
    assert settings.llm_model in repr(build_chat_model())
