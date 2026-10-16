from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from src.core.database import session_factory
from src.core.exceptions import UpstreamError
from src.main import app
from src.modules.knowledge.knowledge_dependencies import get_embeddings
from src.modules.knowledge.knowledge_service import EMBEDDING_MODEL_ID, KnowledgeService, verify_embedding_index
from src.modules.knowledge.models import Document, DocumentChunk
from src.modules.knowledge.schemas import DocumentIngest
from src.modules.knowledge.seed import seed_documents
from tests.fake_embeddings import WordHashEmbeddings

RUNBOOK = {
    "title": "Checkout errors",
    "source_uri": "wiki://checkout-errors",
    "doc_type": "runbook",
    "service_tags": ["checkout"],
    "content": "# Checkout errors\n\n## Diagnose\n\nLook for gateway timeouts in checkout logs.\n",
}


@pytest.fixture(autouse=True)
def _fake_embeddings() -> Iterator[None]:
    app.dependency_overrides[get_embeddings] = WordHashEmbeddings
    yield
    app.dependency_overrides.pop(get_embeddings, None)


async def _seed() -> None:
    await seed_documents(WordHashEmbeddings())


async def test_search_finds_the_runbook_for_the_symptom(client: AsyncClient, regular_headers: dict[str, str]):
    await _seed()

    response = await client.get(
        "/v1/knowledge/search",
        params={"q": "payments p99 latency spike after a deployment", "service": "payments"},
        headers=regular_headers,
    )

    assert response.status_code == 200
    hits = response.json()
    assert len(hits) == 5
    assert hits[0]["source_uri"] == "seed://payments-latency.md"
    assert hits[0]["content"].startswith("Payments latency spike")
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True)


async def test_service_filter_keeps_that_service_and_general_documents(
    client: AsyncClient, superuser_headers: dict[str, str], regular_headers: dict[str, str]
):
    await _seed()
    await client.post("/v1/knowledge/documents", json=RUNBOOK, headers=superuser_headers)

    async def sources(service: str | None) -> set[str]:
        params = {"q": "rollback logs errors timeouts", "limit": 20} | ({"service": service} if service else {})
        response = await client.get("/v1/knowledge/search", params=params, headers=regular_headers)
        return {hit["source_uri"] for hit in response.json()}

    # deployment-rollback.md has no service tags, so it applies to every service.
    assert await sources("checkout") == {"wiki://checkout-errors", "seed://deployment-rollback.md"}
    assert "wiki://checkout-errors" not in await sources("payments")
    assert "wiki://checkout-errors" in await sources(None)


async def test_reingesting_is_idempotent_and_changes_replace_the_document(
    client: AsyncClient, superuser_headers: dict[str, str]
):
    created = await client.post("/v1/knowledge/documents", json=RUNBOOK, headers=superuser_headers)
    assert created.status_code == 200
    assert created.json()["result"] == "created"
    assert created.json()["chunk_count"] == 1

    again = await client.post("/v1/knowledge/documents", json=RUNBOOK, headers=superuser_headers)
    assert again.json() == created.json() | {"result": "unchanged"}

    changed = RUNBOOK | {"content": RUNBOOK["content"] + "\n## Fix\n\nRestart the gateway.\n"}
    updated = await client.post("/v1/knowledge/documents", json=changed, headers=superuser_headers)
    assert updated.json()["result"] == "updated"
    assert updated.json()["document_id"] == created.json()["document_id"]
    assert updated.json()["chunk_count"] == 2

    async with session_factory() as session:
        chunks = (await session.scalars(select(DocumentChunk).order_by(DocumentChunk.chunk_index))).all()
    assert [chunk.content for chunk in chunks] == [
        "Checkout errors > Diagnose\n\nLook for gateway timeouts in checkout logs.",
        "Checkout errors > Fix\n\nRestart the gateway.",
    ]
    assert {chunk.embedding_model for chunk in chunks} == {EMBEDDING_MODEL_ID}


async def test_seeding_twice_changes_nothing():
    first = await seed_documents(WordHashEmbeddings())
    second = await seed_documents(WordHashEmbeddings())

    assert first == {"created": 5}
    assert second == {"unchanged": 5}


async def test_only_superusers_can_ingest(client: AsyncClient, regular_headers: dict[str, str]):
    response = await client.post("/v1/knowledge/documents", json=RUNBOOK, headers=regular_headers)

    assert response.status_code == 403
    async with session_factory() as session:
        assert (await session.scalars(select(Document))).all() == []


async def test_search_requires_authentication(client: AsyncClient):
    assert (await client.get("/v1/knowledge/search", params={"q": "latency"})).status_code == 401


async def test_document_without_text_is_rejected(client: AsyncClient, superuser_headers: dict[str, str]):
    response = await client.post(
        "/v1/knowledge/documents", json=RUNBOOK | {"content": "# Only a heading\n"}, headers=superuser_headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"


async def test_embedding_provider_failure_keeps_the_stored_document():
    class BrokenEmbeddings(WordHashEmbeddings):
        async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
            raise ConnectionError("model server down")

    async with session_factory() as session:
        await KnowledgeService(session, WordHashEmbeddings()).ingest(DocumentIngest(**RUNBOOK))
    async with session_factory() as session:
        changed = DocumentIngest.model_validate(RUNBOOK | {"content": "# Checkout errors\n\nNew text.\n"})
        with pytest.raises(UpstreamError):
            await KnowledgeService(session, BrokenEmbeddings()).ingest(changed)

    async with session_factory() as session:
        chunk = await session.scalar(select(DocumentChunk))
    assert chunk is not None and "gateway timeouts" in chunk.content


async def test_startup_check_rejects_vectors_from_another_model():
    await _seed()
    async with session_factory() as session:
        await verify_embedding_index(session)

        await session.execute(update(DocumentChunk).values(embedding_model="openai:text-embedding-3-small"))
        await session.commit()
        with pytest.raises(RuntimeError, match="openai:text-embedding-3-small"):
            await verify_embedding_index(session)
