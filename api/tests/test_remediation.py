"""Proposals, approvals, execution and verification.

Tests that approve an action really execute it against the demo payments service, so every one of them runs inside
`bad_release` (v2 deployed; the previous version is redeployed afterwards) or resets what it changed.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from src.core import background
from src.core.config import MetricName, RiskLevel, app_config, settings
from src.core.database import session_factory
from src.core.exceptions import ForbiddenError
from src.core.http import http_client
from src.modules.auth.cli import create_superuser
from src.modules.auth.schemas import UserRead
from src.modules.copilot.checkpointer import close_checkpointer
from src.modules.monitoring.monitoring_service import MonitoringService
from src.modules.remediation.approval_policy import ApprovalPolicy
from src.modules.remediation.remediation_service import RemediationService
from tests.copilot_helpers import ask, proposing, run_steps
from tests.fake_chat_model import ScriptedChatModel
from tests.helpers import PASSWORD, auth_headers, eventually

pytestmark = pytest.mark.usefixtures("copilot_data")

DEPLOYMENT_URL = f"{settings.demo_payments_admin_url}/admin/deployments/payments"
TERMINAL = {"verified", "unverified", "failed"}


@pytest.fixture
async def quick_verification(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """One metric check instead of polling for minutes, for tests that aren't about recovery."""
    monkeypatch.setattr(app_config.remediation.verification, "timeout_seconds", 0)
    yield
    # Finish background verification while the patch still applies (e.g. when the test failed early).
    await background.wait_for_all()


@pytest.fixture
async def reset_replicas() -> AsyncIterator[None]:
    yield
    await http_client.post(f"{DEPLOYMENT_URL}/scale", json={"replicas": 1})


async def _demo_deployment() -> dict[str, Any]:
    return (await http_client.get(DEPLOYMENT_URL)).json()


async def _proposed_run(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    response = await ask(client, headers)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "awaiting_approval"
    return run


async def _remediation(client: AsyncClient, headers: dict[str, str], proposal_id: str) -> dict[str, Any]:
    response = await client.get(f"/v1/remediations/{proposal_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _wait_until_finished(client: AsyncClient, headers: dict[str, str], proposal_id: str) -> dict[str, Any]:
    async def finished() -> dict[str, Any]:
        remediation = await _remediation(client, headers, proposal_id)
        assert remediation["status"] in TERMINAL
        return remediation

    return await eventually(finished, within_seconds=240, interval=2)


# --- Approval rules ---


def _user(superuser: bool, active: bool = True) -> UserRead:
    return UserRead(
        id=uuid.uuid4(),
        email="someone@example.com",
        is_superuser=superuser,
        is_active=active,
        created_by_id=None,
        created_at="2026-01-01T00:00:00Z",
    )


@pytest.mark.parametrize(
    ("superuser", "own_run", "superusers", "risk", "can_approve", "can_reject"),
    [
        (False, False, 2, RiskLevel.LOW, True, True),
        (False, True, 2, RiskLevel.HIGH, False, True),  # may cancel their own run's proposal, not approve it
        (False, False, 2, RiskLevel.HIGH, False, False),
        (True, False, 2, RiskLevel.HIGH, True, True),
        (True, True, 2, RiskLevel.HIGH, False, True),  # second pair of eyes required
        (True, True, 1, RiskLevel.HIGH, True, True),  # unless they are the only superuser
        (True, True, 2, RiskLevel.LOW, True, True),
    ],
)
def test_approval_policy(
    superuser: bool, own_run: bool, superusers: int, risk: RiskLevel, can_approve: bool, can_reject: bool
):
    actor = _user(superuser)
    owner_id = actor.id if own_run else uuid.uuid4()
    policy = ApprovalPolicy(actor, active_superuser_count=superusers)

    assert policy.can_approve(risk, owner_id) is can_approve
    assert policy.can_reject(risk, owner_id) is can_reject


def test_inactive_users_can_decide_nothing():
    actor = _user(superuser=True, active=False)
    policy = ApprovalPolicy(actor, active_superuser_count=1)

    assert not policy.can_approve(RiskLevel.LOW, actor.id)
    assert not policy.can_reject(RiskLevel.LOW, actor.id)


# --- Proposals ---


async def test_proposed_action_pauses_the_run_and_nothing_runs_before_approval(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel
):
    llm.handlers["Diagnosis"] = proposing("rollback_deployment")
    before = await _demo_deployment()

    run = await _proposed_run(client, regular_headers)

    remediation = run["remediation"]
    assert remediation["action"] == "rollback_deployment"
    assert remediation["risk_level"] == "high"  # from the catalog, not the LLM
    assert remediation["service"] == "payments"
    assert remediation["status"] == "proposed"
    assert remediation["execution"] is None
    assert run["answer"] and run["completed_at"] is None
    nodes = [step["node"] for step in await run_steps(client, regular_headers, run["id"]) if not step["tool_name"]]
    assert nodes[-1] == "propose_remediation"

    # The service itself refuses to act on an unapproved proposal, whatever calls it.
    async with session_factory() as session:
        with pytest.raises(ForbiddenError):
            await RemediationService(session).execute(uuid.UUID(remediation["id"]))
    assert (await _demo_deployment())["history"] == before["history"]


async def test_invalid_proposal_is_dropped(
    client: AsyncClient, regular_headers: dict[str, str], llm: ScriptedChatModel
):
    llm.handlers["Diagnosis"] = proposing("scale_deployment", replicas=50)

    run = (await ask(client, regular_headers)).json()

    assert run["status"] == "completed"
    assert run["remediation"] is None
    steps = await run_steps(client, regular_headers, run["id"])
    [proposal_step] = [step for step in steps if step["node"] == "propose_remediation" and not step["tool_name"]]
    assert "between 1 and 10" in proposal_step["output"]["rejected_proposal"]


async def test_rejection_finishes_the_run_without_acting(
    client: AsyncClient, regular_headers: dict[str, str], superuser_headers: dict[str, str], llm: ScriptedChatModel
):
    llm.handlers["Diagnosis"] = proposing("rollback_deployment")
    before = await _demo_deployment()
    run = await _proposed_run(client, regular_headers)
    proposal_id = run["remediation"]["id"]

    # The person who asked may call off a high-risk action they couldn't approve.
    response = await client.post(
        f"/v1/remediations/{proposal_id}/reject", json={"comment": "Not now"}, headers=regular_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["approval"]["comment"] == "Not now"
    run = (await client.get(f"/v1/copilot/runs/{run['id']}", headers=regular_headers)).json()
    assert run["status"] == "rejected"
    assert run["remediation"]["execution"] is None
    assert (await _demo_deployment())["history"] == before["history"]
    again = await client.post(f"/v1/remediations/{proposal_id}/approve", json={}, headers=superuser_headers)
    assert again.status_code == 409


# --- Who may approve ---


async def test_regular_user_can_approve_low_risk_but_not_high_risk(
    client: AsyncClient,
    regular_headers: dict[str, str],
    llm: ScriptedChatModel,
    quick_verification: None,
    reset_replicas: None,
):
    llm.handlers["Diagnosis"] = proposing("rollback_deployment")
    high = (await _proposed_run(client, regular_headers))["remediation"]
    denied = await client.post(f"/v1/remediations/{high['id']}/approve", json={}, headers=regular_headers)
    assert denied.status_code == 403

    llm.handlers["Diagnosis"] = proposing("scale_deployment", replicas=2)
    low = (await _proposed_run(client, regular_headers))["remediation"]
    assert low["risk_level"] == "low"
    approved = await client.post(f"/v1/remediations/{low['id']}/approve", json={}, headers=regular_headers)
    assert approved.status_code == 202

    finished = await _wait_until_finished(client, regular_headers, low["id"])
    assert finished["execution"]["result"]["replicas"] == 2
    assert (await _demo_deployment())["replicas"] == 2


async def test_superuser_needs_a_second_superuser_for_their_own_high_risk_run(
    client: AsyncClient,
    superuser_headers: dict[str, str],
    llm: ScriptedChatModel,
    quick_verification: None,
    bad_release: None,
):
    llm.handlers["Diagnosis"] = proposing("rollback_deployment")
    proposal_id = (await _proposed_run(client, superuser_headers))["remediation"]["id"]
    await create_superuser("second@example.com", PASSWORD)

    own = await client.post(f"/v1/remediations/{proposal_id}/approve", json={}, headers=superuser_headers)
    assert own.status_code == 403

    second = await auth_headers(client, "second@example.com")
    approved = await client.post(f"/v1/remediations/{proposal_id}/approve", json={}, headers=second)
    assert approved.status_code == 202
    await _wait_until_finished(client, second, proposal_id)


async def test_sole_superuser_can_approve_their_own_high_risk_run(
    client: AsyncClient,
    superuser_headers: dict[str, str],
    llm: ScriptedChatModel,
    quick_verification: None,
    bad_release: None,
):
    llm.handlers["Diagnosis"] = proposing("rollback_deployment")
    proposal_id = (await _proposed_run(client, superuser_headers))["remediation"]["id"]

    response = await client.post(f"/v1/remediations/{proposal_id}/approve", json={}, headers=superuser_headers)

    assert response.status_code == 202
    finished = await _wait_until_finished(client, superuser_headers, proposal_id)
    assert finished["execution"]["result"]["version"] == "v1"


# --- The whole loop, live ---


async def test_approved_rollback_runs_once_and_the_service_recovers(
    client: AsyncClient,
    regular_headers: dict[str, str],
    superuser_headers: dict[str, str],
    llm: ScriptedChatModel,
    monkeypatch: pytest.MonkeyPatch,
    bad_release: None,
):
    monkeypatch.setattr(app_config.remediation.verification, "poll_seconds", 5)

    # Act only once the bad release is visible in the metrics, so verification has to see a real recovery.
    async def latency_spiked() -> None:
        series = await MonitoringService().get_metric("payments", MetricName.LATENCY_P99_SECONDS, 5)
        assert series.points and series.points[-1].value > 0.5

    await eventually(latency_spiked)
    llm.handlers["Diagnosis"] = proposing("rollback_deployment")
    run = await _proposed_run(client, regular_headers)
    proposal_id = run["remediation"]["id"]
    revisions_before = len((await _demo_deployment())["history"])

    # Two approvals racing: exactly one wins.
    first, second = await asyncio.gather(
        client.post(f"/v1/remediations/{proposal_id}/approve", json={"comment": "go"}, headers=superuser_headers),
        client.post(f"/v1/remediations/{proposal_id}/approve", json={}, headers=superuser_headers),
    )
    assert sorted([first.status_code, second.status_code]) == [202, 409]

    finished = await _wait_until_finished(client, regular_headers, proposal_id)

    assert finished["status"] == "verified", finished["execution"]["verification"]
    verification = finished["execution"]["verification"]
    assert verification["passed"]
    assert verification["waited_seconds"] >= 10  # it watched the service recover; it wasn't already healthy
    assert {check["metric"] for check in verification["checks"]} == {"latency_p99_seconds", "error_ratio"}
    assert all(check["value"] <= check["threshold"] for check in verification["checks"])
    deployment = await _demo_deployment()
    assert deployment["version"] == "v1"
    assert len(deployment["history"]) == revisions_before + 1  # rolled back exactly once

    run = (await client.get(f"/v1/copilot/runs/{run['id']}", headers=regular_headers)).json()
    assert run["status"] == "completed"
    assert run["completed_at"] is not None
    steps = await run_steps(client, regular_headers, run["id"])
    nodes = [step["node"] for step in steps if not step["tool_name"]]
    assert nodes[-3:] == ["await_approval", "execute_action", "verify_outcome"]
    assert not [step for step in steps if step["error"]]


async def test_paused_run_resumes_after_a_restart(
    client: AsyncClient,
    regular_headers: dict[str, str],
    superuser_headers: dict[str, str],
    llm: ScriptedChatModel,
    quick_verification: None,
    bad_release: None,
):
    llm.handlers["Diagnosis"] = proposing("rollback_deployment")
    run = await _proposed_run(client, regular_headers)
    # Drop every in-memory piece of graph state, as a restart would; only the Postgres checkpoint remains.
    await close_checkpointer()

    response = await client.post(
        f"/v1/remediations/{run['remediation']['id']}/approve", json={}, headers=superuser_headers
    )

    assert response.status_code == 202
    finished = await _wait_until_finished(client, regular_headers, run["remediation"]["id"])
    assert finished["execution"]["result"]["version"] == "v1"
    run = (await client.get(f"/v1/copilot/runs/{run['id']}", headers=regular_headers)).json()
    assert run["status"] == "completed"
    assert run["answer"] == "Latency rose after the v2 release."  # state from before the restart


async def test_unexpected_failure_after_approval_fails_the_proposal_too(
    client: AsyncClient,
    superuser_headers: dict[str, str],
    llm: ScriptedChatModel,
    monkeypatch: pytest.MonkeyPatch,
    bad_release: None,
):
    async def broken_check(*_args: Any) -> None:
        raise RuntimeError("bug in verification")

    monkeypatch.setattr(RemediationService, "_check_metrics", broken_check)
    llm.handlers["Diagnosis"] = proposing("rollback_deployment")
    run = await _proposed_run(client, superuser_headers)

    await client.post(f"/v1/remediations/{run['remediation']['id']}/approve", json={}, headers=superuser_headers)
    await background.wait_for_all()

    run = (await client.get(f"/v1/copilot/runs/{run['id']}", headers=superuser_headers)).json()
    assert run["status"] == "failed"
    # Not left "executing" forever: the rollback happened, but its outcome is unknown.
    assert run["remediation"]["status"] == "failed"
    assert run["remediation"]["execution"]["result"]["version"] == "v1"


# --- Visibility ---


async def test_users_see_their_own_proposals_and_everyones_low_risk_ones(
    client: AsyncClient, superuser_headers: dict[str, str], regular_headers: dict[str, str], llm: ScriptedChatModel
):
    llm.handlers["Diagnosis"] = proposing("rollback_deployment")
    high = (await _proposed_run(client, superuser_headers))["remediation"]
    llm.handlers["Diagnosis"] = proposing("scale_deployment", replicas=3)
    low = (await _proposed_run(client, superuser_headers))["remediation"]

    visible = await client.get("/v1/remediations", params={"status": "proposed"}, headers=regular_headers)
    assert [item["id"] for item in visible.json()] == [low["id"]]
    assert (await client.get(f"/v1/remediations/{high['id']}", headers=regular_headers)).status_code == 404

    everything = await client.get("/v1/remediations", headers=superuser_headers)
    assert {item["id"] for item in everything.json()} == {low["id"], high["id"]}
