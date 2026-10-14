from typing import Any

from httpx import AsyncClient, Response

QUESTION = "Why is the payments service showing a latency spike?"


def classify_as(category: str, service: str | None = "payments", window_minutes: int = 10):
    return lambda _prompt: {"category": category, "service": service, "window_minutes": window_minutes}


def diagnosis_from(prompt: str, proposed_action: dict[str, Any] | None = None) -> dict[str, Any]:
    """Stands in for a model that reads the evidence: it only blames v2 if the prompt shows v2 running."""
    blames_release = "Current version v2" in prompt
    return {
        "answer": "Latency rose after the v2 release." if blames_release else "No clear cause.",
        "likely_cause": "Release v2 exhausted the DB pool" if blames_release else "unknown",
        "confidence": "high" if blames_release else "low",
        "evidence": ["p99 latency over 2 s", "v2 deployed shortly before"] if blames_release else [],
        "recommended_actions": ["Roll back to v1 (needs superuser approval)"] if blames_release else [],
        "proposed_action": proposed_action,
    }


def proposing(action: str, **params: Any):
    """A Diagnosis handler whose diagnosis proposes `action`."""
    proposed = {"action": action, "rationale": f"Runbook says to {action} here.", **params}
    return lambda prompt: diagnosis_from(prompt, proposed)


async def ask(client: AsyncClient, headers: dict[str, str], question: str = QUESTION) -> Response:
    return await client.post("/v1/copilot/runs", json={"question": question}, headers=headers)


async def run_steps(client: AsyncClient, headers: dict[str, str], run_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"/v1/copilot/runs/{run_id}/steps", headers=headers)
    assert response.status_code == 200
    return response.json()
