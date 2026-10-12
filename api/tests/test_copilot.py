"""Copilot runs with every real component except the LLM, which is scripted.

The scripted model can't tell us whether a real model reasons well (that's what the evals are for). These tests check
everything around it: routing, evidence gathering from the live stack, what the LLM is shown, and the audit trail.
"""

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient

from src.core.config import MetricName
from src.core.database import session_factory
from src.main import app
from src.modules.copilot.copilot_dependencies import get_chat_model, get_classifier_model
from src.modules.incidents.incident_service import IncidentService
from src.modules.incidents.seed import load_seed_incidents
from src.modules.knowledge.knowledge_dependencies import get_embeddings
from src.modules.knowledge.seed import seed_documents
from src.modules.monitoring.monitoring_service import MonitoringService
from tests.fake_chat_model import ScriptedChatModel
from tests.fake_embeddings import WordHashEmbeddings
from tests.helpers import PASSWORD, auth_headers, eventually

QUESTION = "Why is the payments service showing a latency spike?"


def classify_as(category: str, service: str | None = "payments", window_minutes: int = 10):
    return lambda _prompt: {"category": category, "service": service, "window_minutes": window_minutes}


def diagnosis_from(prompt: str) -> dict[str, Any]:
    """Stands in for a model that reads the evidence: it only blames v2 if the prompt shows v2 running."""
    blames_release = "Current version v2" in prompt
    return {
        "answer": "Latency rose after the v2 release." if blames_release else "No clear cause.",
        "likely_cause": "Release v2 exhausted the DB pool" if blames_release else "unknown",
        "confidence": "high" if blames_release else "low",
        "evidence": ["p99 latency over 2 s", "v2 deployed shortly before"] if blames_release else [],
        "recommended_actions": ["Roll back to v1 (needs superuser approval)"] if blames_release else [],
    }


@pytest.fixture
def llm() -> Iterator[ScriptedChatModel]:
    model = ScriptedChatModel(
        handlers={
            "Classification": classify_as("investigate"),
            "Diagnosis": diagnosis_from,
            "text": lambda _prompt: "Roll back via the deployment rollback runbook.",
        }
    )
    app.dependency_overrides[get_chat_model] = lambda: model
    app.dependency_overrides[get_classifier_model] = lambda: model
    app.dependency_overrides[get_embeddings] = WordHashEmbeddings
    yield model


@pytest.fixture(autouse=True)
async def _seed_data() -> None:
    await seed_documents(WordHashEmbeddings())
    async with session_factory() as session:
        await IncidentService(session).seed(load_seed_incidents(datetime.now(UTC)))


async def _ask(client: AsyncClient, headers: dict[str, str], question: str = QUESTION):
    return await client.post("/v1/copilot/runs", json={"question": question}, headers=headers)


async def _steps(client: AsyncClient, headers: dict[str, str], run_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"/v1/copilot/runs/{run_id}/steps", headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_investigation_shows_the_llm_the_live_evidence_of_a_bad_release(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel, bad_release: None
):
    async def latency_spiked() -> None:
        series = await MonitoringService().get_metric("payments", MetricName.LATENCY_P99_SECONDS, 5)
        assert series.points and series.points[-1].value > 0.5

    await eventually(latency_spiked)

    response = await _ask(client, regular_headers)

    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "completed"
    assert run["answer"] == "Latency rose after the v2 release."
    assert run["classification"] == {"category": "investigate", "service": "payments", "window_minutes": 10}
    assert run["diagnosis"]["confidence"] == "high"

    [prompt] = llm.prompts["Diagnosis"]
    assert "Current version v2" in prompt
    assert "connection pool exhausted" in prompt
    assert '<document title="Payments latency spike"' in prompt
    assert "Payments latency spike after release" in prompt  # the seeded past incident
    assert QUESTION in prompt
    p99_now = float(re.search(r"p99 latency: now ([\d.]+)s", prompt).group(1))
    assert p99_now > 0.5

    steps = await _steps(client, regular_headers, run["id"])
    assert not [step for step in steps if step["error"]]
    nodes = {step["node"] for step in steps if step["tool_name"] is None}
    assert nodes == {"classify", "retrieve_runbooks", "gather_evidence", "diagnose"}
    tools = {step["tool_name"] for step in steps if step["node"] == "gather_evidence" and step["tool_name"]}
    assert tools == {*(f"metric:{name}" for name in MetricName), "error_logs", "slow_traces", "deployment", "incidents"}
    [diagnose_call] = [step for step in steps if step["node"] == "diagnose" and step["tool_name"] == "llm"]
    # The audit trail holds exactly what the model was sent.
    assert "\n\n".join(message["content"] for message in diagnose_call["input"]) == prompt
    assert diagnose_call["output"]["likely_cause"] == "Release v2 exhausted the DB pool"


async def test_knowledge_question_is_answered_from_documents_without_live_data(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel
):
    llm.handlers["Classification"] = classify_as("knowledge", service=None)

    run = (await _ask(client, regular_headers, "How do I roll back a deployment?")).json()

    assert run["status"] == "completed"
    assert run["answer"] == "Roll back via the deployment rollback runbook."
    assert run["diagnosis"] is None
    assert '<document title="Rolling back a deployment"' in llm.prompts["text"][0]
    nodes = [step["node"] for step in await _steps(client, regular_headers, run["id"]) if step["tool_name"] is None]
    assert nodes == ["classify", "retrieve_documents", "answer_knowledge"]


async def test_out_of_scope_questions_are_declined_without_further_llm_calls(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel
):
    llm.handlers["Classification"] = classify_as("out_of_scope", service=None)

    run = (await _ask(client, regular_headers, "Write me a poem about the sea")).json()

    assert run["answer"].startswith("I can only help with operating our services")
    assert set(llm.prompts) == {"Classification"}


@pytest.mark.parametrize("service", [None, "Payments Service!!", "a b"])
async def test_investigation_without_a_usable_service_asks_for_one(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel, service: str | None
):
    llm.handlers["Classification"] = classify_as("investigate", service=service, window_minutes=99_999)

    run = (await _ask(client, regular_headers, "Why is everything slow?")).json()

    assert run["answer"].startswith("Which service should I look at?")
    # The classifier's output is sanitised before use.
    assert run["classification"] == {"category": "investigate", "service": None, "window_minutes": 1440}
    assert "Diagnosis" not in llm.prompts


async def test_unavailable_evidence_is_reported_to_the_llm_instead_of_failing_the_run(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel
):
    # The demo deployment backend only knows "payments".
    llm.handlers["Classification"] = classify_as("investigate", service="inventory")

    run = (await _ask(client, regular_headers, "Is the inventory service healthy?")).json()

    assert run["status"] == "completed"
    [prompt] = llm.prompts["Diagnosis"]
    assert "## Unavailable sources\n- deployment:" in prompt
    assert "- p99 latency: no data" in prompt
    steps = await _steps(client, regular_headers, run["id"])
    [deployment_step] = [step for step in steps if step["tool_name"] == "deployment"]
    assert "not found" in deployment_step["error"]


async def test_llm_failure_fails_the_run_and_keeps_its_record(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel
):
    def unreachable(_prompt: str) -> Any:
        raise ConnectionError("model server down")

    llm.handlers["Classification"] = unreachable

    response = await _ask(client, regular_headers)

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "upstream_error"
    run = (await client.get(f"/v1/copilot/runs/{error['details']['run_id']}", headers=regular_headers)).json()
    assert run["status"] == "failed"
    assert run["error"] == "LLM provider failed"
    assert run["completed_at"] is not None
    steps = await _steps(client, regular_headers, run["id"])
    assert [(step["node"], step["tool_name"]) for step in steps if step["error"]] == [
        ("classify", "llm"),
        ("classify", None),
    ]


async def test_users_see_only_their_own_runs_and_superusers_see_all(
    client: AsyncClient,
    regular_headers: dict[str, str],
    superuser_headers: dict[str, str],
    llm: ScriptedChatModel,
):
    llm.handlers["Classification"] = classify_as("out_of_scope", service=None)
    run_id = (await _ask(client, regular_headers, "Tell me a joke")).json()["id"]
    await client.post("/v1/users", json={"email": "other@example.com", "password": PASSWORD}, headers=superuser_headers)
    other_headers = await auth_headers(client, "other@example.com")

    assert (await client.get(f"/v1/copilot/runs/{run_id}", headers=other_headers)).status_code == 404
    assert (await client.get(f"/v1/copilot/runs/{run_id}/steps", headers=other_headers)).status_code == 404
    assert (await client.get("/v1/copilot/runs", headers=other_headers)).json() == []

    assert (await client.get(f"/v1/copilot/runs/{run_id}", headers=superuser_headers)).status_code == 200
    everyone = (await client.get("/v1/copilot/runs", headers=superuser_headers)).json()
    assert [run["id"] for run in everyone] == [run_id]
    own = (await client.get("/v1/copilot/runs", headers=regular_headers)).json()
    assert [run["id"] for run in own] == [run_id]


async def test_runs_require_authentication(client: AsyncClient):
    assert (await client.post("/v1/copilot/runs", json={"question": QUESTION})).status_code == 401
    assert (await client.get("/v1/copilot/runs")).status_code == 401
