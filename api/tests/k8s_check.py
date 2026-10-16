"""Checks the Kubernetes deployment backend from inside the cluster: `make k8s-verify` runs it in the API pod.

Uses the pod's own service account, so it proves the RBAC as well as the adapter. Expects `make k8s-verify` to have
just released v2 of the demo payments Deployment on top of v1. Exits non-zero on the first failed check.
"""

import asyncio
import sys

from src.core.exceptions import AppError
from src.modules.deployments.deployment_service import DeploymentService
from src.modules.deployments.kubernetes_deployment_adapter import KubernetesDeploymentAdapter

SERVICE = "payments"


async def main() -> None:
    deployments = DeploymentService()

    state = await deployments.get_deployment(SERVICE)
    versions = [revision.version for revision in state.history]
    _check(state.version == "v2" and versions[:2] == ["v2", "v1"], f"sees the v2 release on top of v1: {versions}")
    released_at, previous_at = state.history[0].deployed_at, state.history[1].deployed_at
    assert released_at and previous_at, f"both releases have a time: {state.history[:2]}"
    _check(released_at > previous_at, f"release time is the newest: {released_at}")

    state = await deployments.rollback(SERVICE)
    _check(state.version == "v1", f"rollback restores v1: now {state.version}")
    rollback = state.history[0]
    _check(rollback.version == "v1", f"the rollback is the newest revision: {rollback}")
    _check(
        rollback.deployed_at is not None and rollback.deployed_at >= released_at,
        f"the rollback is dated no earlier than the release it undid: {rollback.deployed_at}",
    )

    revision_before = state.history[0].revision
    state = await deployments.restart(SERVICE)
    _check(
        state.version == "v1" and state.history[0].revision == revision_before + 1,
        f"restart makes a new revision of the same version: {state.history[0]}",
    )
    _check(state.history[1].deployed_at is None, f"the superseded rollback's time is unknown: {state.history[1]}")

    state = await deployments.scale(SERVICE, 2)
    _check(state.replicas == 2, f"scales to 2: {state.replicas}")
    state = await deployments.scale(SERVICE, 1)
    _check(state.replicas == 1, f"scales back to 1: {state.replicas}")

    await _expect_refused(deployments.get_deployment("no-such-service"), "an unknown service is reported as not found")
    # RBAC covers the payments namespace only, not even the copilot's own.
    elsewhere = KubernetesDeploymentAdapter("copilot")
    await _expect_refused(elsewhere.get_deployment("api"), "reading Deployments outside payments is forbidden")
    await _expect_refused(elsewhere.scale("api", 5), "changing Deployments outside payments is forbidden")
    print("All Kubernetes checks passed.")


async def _expect_refused(call, description: str) -> None:
    try:
        await call
    except AppError as exc:
        _check(True, f"{description}: {exc.message}")
        return
    _check(False, f"{description}: the call succeeded")


def _check(passed: bool, description: str) -> None:
    print(f"{'ok  ' if passed else 'FAIL'} {description}", flush=True)
    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
