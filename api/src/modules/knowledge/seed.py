"""Ingest seed/documents/*.md: `python -m src.modules.knowledge.seed`. Safe to re-run; unchanged files are skipped.

Each file starts with YAML front matter (title, doc_type, service_tags) between `---` lines.
"""

import asyncio
import sys
from collections import Counter
from pathlib import Path

import yaml
from langchain_core.embeddings import Embeddings

from src.core.config import API_ROOT, settings
from src.core.database import engine, session_factory
from src.core.exceptions import AppError
from src.core.llm import build_embeddings
from src.core.logging import configure_logging
from src.modules.knowledge.knowledge_service import KnowledgeService
from src.modules.knowledge.schemas import DocumentIngest

SEED_DIR = API_ROOT / "seed" / "documents"


def load_seed_document(path: Path) -> DocumentIngest:
    _, front_matter, body = path.read_text().split("---\n", 2)
    return DocumentIngest(**yaml.safe_load(front_matter), source_uri=f"seed://{path.name}", content=body)


async def seed_documents(embeddings: Embeddings) -> Counter[str]:
    """Returns how many documents were created, updated and unchanged."""
    results: Counter[str] = Counter()
    async with session_factory() as session:
        service = KnowledgeService(session, embeddings)
        for path in sorted(SEED_DIR.glob("*.md")):
            results[(await service.ingest(load_seed_document(path))).result] += 1
    return results


async def main() -> None:
    try:
        results = await seed_documents(build_embeddings())
    except AppError as exc:
        sys.exit(f"error: {exc.message} {exc.details or ''}; check the EMBEDDING_* settings and that the provider runs")
    finally:
        await engine.dispose()
    print("Documents: " + ", ".join(f"{count} {result}" for result, count in sorted(results.items())))


if __name__ == "__main__":
    configure_logging(settings.log_level)
    asyncio.run(main())
