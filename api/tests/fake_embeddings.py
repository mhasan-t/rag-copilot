import hashlib
import math
import re

from langchain_core.embeddings import Embeddings

from src.core.config import settings


class WordHashEmbeddings(Embeddings):
    """Deterministic stand-in for a real embedding model: texts sharing more words get more similar vectors.

    Good enough to test the retrieval pipeline (chunking, storage, ranking, filters) without a model server;
    retrieval quality with real models is measured by the evals, not by unit tests.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    @staticmethod
    def _embed(text: str) -> list[float]:
        vector = [0.0] * settings.embedding_dimensions
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % len(vector)] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]
