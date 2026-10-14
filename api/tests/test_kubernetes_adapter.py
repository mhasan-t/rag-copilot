"""How Kubernetes objects become deployment state and rollback targets. `make k8s-verify` covers the real cluster."""

from datetime import UTC, datetime, timedelta

import pytest
from kubernetes_asyncio.client import (
    V1Container,
    V1Deployment,
    V1DeploymentCondition,
    V1DeploymentSpec,
    V1DeploymentStatus,
    V1LabelSelector,
    V1ObjectMeta,
    V1OwnerReference,
    V1PodSpec,
    V1PodTemplateSpec,
    V1ReplicaSet,
    V1ReplicaSetSpec,
)

from src.core.exceptions import ConflictError
from src.modules.deployments.kubernetes_deployment_adapter import deployment_state, previous_template, version_of

T0 = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
DEPLOYMENT_UID = "deployment-uid"
_OWNER = V1OwnerReference(api_version="apps/v1", kind="Deployment", name="payments", uid=DEPLOYMENT_UID)


def _template(version: str | None = None, image: str = "registry.example.com/payments:1.4.2") -> V1PodTemplateSpec:
    labels = {"app.kubernetes.io/name": "payments", "pod-template-hash": "abc123"}
    if version:
        labels["app.kubernetes.io/version"] = version
    return V1PodTemplateSpec(
        metadata=V1ObjectMeta(labels=labels), spec=V1PodSpec(containers=[V1Container(name="app", image=image)])
    )


def _replica_set(revision: int, version: str, created: datetime, reused_from: int | None = None) -> V1ReplicaSet:
    """`reused_from`: the revision this ReplicaSet had before a rollback brought it back."""
    annotations = {"deployment.kubernetes.io/revision": str(revision)}
    if reused_from is not None:
        annotations["deployment.kubernetes.io/revision-history"] = str(reused_from)
    return V1ReplicaSet(
        metadata=V1ObjectMeta(
            name=f"payments-{revision}",
            annotations=annotations,
            creation_timestamp=created,
            owner_references=[_OWNER],
        ),
        spec=V1ReplicaSetSpec(selector=V1LabelSelector(), template=_template(version)),
    )


def _deployment(revision: int, version: str, progressed_at: datetime | None = None) -> V1Deployment:
    progressing = V1DeploymentCondition(type="Progressing", status="True", last_update_time=progressed_at)
    annotations = {"deployment.kubernetes.io/revision": str(revision)}
    return V1Deployment(
        metadata=V1ObjectMeta(name="payments", uid=DEPLOYMENT_UID, annotations=annotations),
        spec=V1DeploymentSpec(replicas=3, selector=V1LabelSelector(), template=_template(version)),
        status=V1DeploymentStatus(conditions=[progressing] if progressed_at else []),
    )


def test_state_lists_revisions_newest_first_with_their_versions():
    replica_sets = [_replica_set(1, "v1", T0), _replica_set(2, "v2", T0 + timedelta(hours=1))]

    state = deployment_state(_deployment(2, "v2"), replica_sets)

    assert (state.name, state.version, state.replicas) == ("payments", "v2", 3)
    assert [(r.revision, r.version, r.deployed_at) for r in state.history] == [
        (2, "v2", T0 + timedelta(hours=1)),
        (1, "v1", T0),
    ]


def test_a_current_rollback_is_dated_by_its_rollout():
    # `rollout undo` reuses v1's old ReplicaSet and renumbers it 1 -> 3; its creation time is from the first rollout.
    replica_sets = [_replica_set(3, "v1", T0, reused_from=1), _replica_set(2, "v2", T0 + timedelta(hours=1))]
    rolled_back_at = T0 + timedelta(hours=2)

    state = deployment_state(_deployment(3, "v1", progressed_at=rolled_back_at), replica_sets)

    assert [(r.revision, r.deployed_at) for r in state.history] == [(3, rolled_back_at), (2, T0 + timedelta(hours=1))]


def test_a_rollback_read_before_its_rollout_progressed_is_never_dated_before_the_revision_it_replaced():
    replica_sets = [_replica_set(3, "v1", T0, reused_from=1), _replica_set(2, "v2", T0 + timedelta(hours=1))]

    # The Progressing condition still describes v2's rollout.
    state = deployment_state(_deployment(2, "v2", progressed_at=T0 + timedelta(hours=1)), replica_sets)

    assert state.history[0].revision == 3  # the newest ReplicaSet is current, even before the Deployment says so
    assert state.history[0].deployed_at == T0 + timedelta(hours=1)


def test_an_older_rollback_has_an_unknown_time_rather_than_a_misleading_one():
    replica_sets = [
        _replica_set(4, "v3", T0 + timedelta(hours=3)),
        _replica_set(3, "v1", T0, reused_from=1),
        _replica_set(2, "v2", T0 + timedelta(hours=1)),
    ]

    state = deployment_state(_deployment(4, "v3"), replica_sets)

    assert [(r.revision, r.deployed_at) for r in state.history] == [
        (4, T0 + timedelta(hours=3)),
        (3, None),
        (2, T0 + timedelta(hours=1)),
    ]


def test_rollback_target_is_the_newest_older_revision_without_the_hash_label():
    replica_sets = [_replica_set(1, "v1", T0), _replica_set(2, "v2", T0), _replica_set(3, "v3", T0)]

    template = previous_template(_deployment(3, "v3"), replica_sets)

    assert template.metadata.labels == {"app.kubernetes.io/name": "payments", "app.kubernetes.io/version": "v2"}


def test_rollback_needs_an_older_revision():
    with pytest.raises(ConflictError, match="No previous revision"):
        previous_template(_deployment(1, "v1"), [_replica_set(1, "v1", T0)])


@pytest.mark.parametrize(
    ("version_label", "image", "expected"),
    [
        ("v7", "payments:1.0", "v7"),
        (None, "registry.example.com:5000/team/payments:1.4.2", "1.4.2"),
        (None, "registry.example.com:5000/team/payments", "latest"),
        (None, "payments@sha256:0123abcd", "sha256:0123abcd"),
    ],
    ids=["label-wins", "tag-after-registry-port", "no-tag", "digest"],
)
def test_version_comes_from_the_label_or_else_the_image(version_label: str | None, image: str, expected: str):
    assert version_of(_template(version_label, image)) == expected
