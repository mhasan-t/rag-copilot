from functools import cache

from langchain_core.embeddings import Embeddings

from src.core.llm import build_embeddings


@cache
def get_embeddings() -> Embeddings:
    """One embeddings client for the process; tests override this dependency with a fake."""
    return build_embeddings()
