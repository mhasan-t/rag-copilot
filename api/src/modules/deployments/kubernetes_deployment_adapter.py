import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from aiohttp import ClientError
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient, ApiException, V1Deployment, V1PodTemplateSpec, V1ReplicaSet

from src.core.config import settings
from src.core.exceptions import ConflictError, NotFoundError, UpstreamError
from src.modules.deployments.schemas import DeploymentRevision, DeploymentState

# Set by the Deployment controller on the Deployment and its ReplicaSets; one ReplicaSet per pod template version.
REVISION_ANNOTATION = "deployment.kubernetes.io/revision"
# Recommended label for the version of the app a pod runs; preferred over guessing from the image tag.
VERSION_LABEL = "app.kubernetes.io/version"
# Set on a ReplicaSet that a rollback brought back, listing the revision numbers it had before.
REVISION_HISTORY_ANNOTATION = "deployment.kubernetes.io/revision-history"
# Added by the ReplicaSet controller to tell its pods apart; must not be copied into a Deployment's template.
POD_TEMPLATE_HASH_LABEL = "pod-template-hash"
RESTARTED_AT_ANNOTATION = "kubectl.kubernetes.io/restartedAt"

_configuration_lock = asyncio.Lock()
_configuration: client.Configuration | None = None


class KubernetesDeploymentAdapter:
    """Deployments in one namespace (DEPLOYMENT_BACKEND=kubernetes); a service name is a Deployment name.

    Needs only get/list/patch on deployments and get/list on replicasets in that namespace (see deploy/k8s).
    """

    def __init__(self, namespace: str):
        self._namespace = namespace

    async def get_deployment(self, name: str) -> DeploymentState:
        async with _apps_api() as apps:
            deployment, replica_sets = await self._read(apps, name)
        return deployment_state(deployment, replica_sets)

    async def rollback(self, name: str) -> DeploymentState:
        """What `kubectl rollout undo` does: put the previous revision's pod template back."""
        async with _apps_api() as apps:
            deployment, replica_sets = await self._read(apps, name)
            template = apps.api_client.sanitize_for_serialization(previous_template(deployment, replica_sets))
            patch = [{"op": "replace", "path": "/spec/template", "value": template}]
            await _call(apps.patch_namespaced_deployment(name, self._namespace, patch))
        return await self.get_deployment(name)

    async def restart(self, name: str) -> DeploymentState:
        """What `kubectl rollout restart` does: change a template annotation, so every pod is replaced."""
        restarted_at = {RESTARTED_AT_ANNOTATION: datetime.now(UTC).isoformat()}
        patch = {"spec": {"template": {"metadata": {"annotations": restarted_at}}}}
        async with _apps_api() as apps:
            await _call(apps.patch_namespaced_deployment(name, self._namespace, patch))
        return await self.get_deployment(name)

    async def scale(self, name: str, replicas: int) -> DeploymentState:
        async with _apps_api() as apps:
            await _call(apps.patch_namespaced_deployment(name, self._namespace, {"spec": {"replicas": replicas}}))
        return await self.get_deployment(name)

    async def _read(self, apps: client.AppsV1Api, name: str) -> tuple[V1Deployment, list[V1ReplicaSet]]:
        deployment = await _call(apps.read_namespaced_deployment(name, self._namespace))
        selector = ",".join(f"{key}={value}" for key, value in deployment.spec.selector.match_labels.items())
        replica_sets = await _call(apps.list_namespaced_replica_set(self._namespace, label_selector=selector))
        # The selector can match ReplicaSets of other Deployments; only this one's own count as its history.
        return deployment, [rs for rs in replica_sets.items if _owned_by(rs, deployment)]


def deployment_state(deployment: V1Deployment, replica_sets: list[V1ReplicaSet]) -> DeploymentState:
    """The Deployment's current version and its revisions, newest first."""
    revisions: list[DeploymentRevision] = []
    # Oldest first, so each revision can be bounded by the one before it.
    ordered = sorted((rs for rs in replica_sets if _revision(rs.metadata) > 0), key=lambda rs: _revision(rs.metadata))
    for index, rs in enumerate(ordered):
        is_current = index == len(ordered) - 1
        previous = revisions[-1].deployed_at if revisions else None
        revisions.append(
            DeploymentRevision(
                revision=_revision(rs.metadata),
                version=version_of(rs.spec.template),
                deployed_at=_deployed_at(rs, deployment, is_current, previous),
            )
        )
    return DeploymentState(
        name=deployment.metadata.name,
        version=version_of(deployment.spec.template),
        replicas=deployment.spec.replicas or 0,
        history=list(reversed(revisions)),
    )


def previous_template(deployment: V1Deployment, replica_sets: list[V1ReplicaSet]) -> V1PodTemplateSpec:
    """The pod template of the newest revision before the current one, ready to put back on the Deployment."""
    current = _revision(deployment.metadata)
    older = [rs for rs in replica_sets if 0 < _revision(rs.metadata) < current]
    if not older:
        raise ConflictError("No previous revision to roll back to", details={"deployment": deployment.metadata.name})
    template = max(older, key=lambda rs: _revision(rs.metadata)).spec.template
    labels = {k: v for k, v in (template.metadata.labels or {}).items() if k != POD_TEMPLATE_HASH_LABEL}
    template.metadata.labels = labels
    return template


def version_of(template: V1PodTemplateSpec) -> str:
    """The app.kubernetes.io/version label, else the first container's image tag (or digest)."""
    if version := (template.metadata.labels or {}).get(VERSION_LABEL):
        return version
    image = template.spec.containers[0].image
    if "@" in image:
        return image.rsplit("@", 1)[1]
    name, _, tag = image.rpartition(":")
    return tag if name and "/" not in tag else "latest"


def _deployed_at(
    rs: V1ReplicaSet, deployment: V1Deployment, is_current: bool, previous: datetime | None
) -> datetime | None:
    """When a revision went live. Kubernetes doesn't record this, so it's derived, or None when it can't be.

    A new ReplicaSet is created for a new pod template, so its creation time is the answer. A rollback instead reuses
    the old ReplicaSet and renumbers it (keeping its old numbers in a revision-history annotation): its creation time
    is from the first rollout. For the current revision, the time the rollout last progressed is used, never earlier
    than the revision before it. For an older reused revision, nothing records when it went live.
    """
    created = rs.metadata.creation_timestamp
    if REVISION_HISTORY_ANNOTATION not in (rs.metadata.annotations or {}):
        return created
    if not is_current:
        return None
    progressed = [
        condition.last_update_time
        for condition in deployment.status.conditions or []
        if condition.type == "Progressing" and condition.last_update_time
    ]
    return max([created, *progressed, *([previous] if previous else [])])


def _owned_by(rs: V1ReplicaSet, deployment: V1Deployment) -> bool:
    return any(owner.uid == deployment.metadata.uid for owner in rs.metadata.owner_references or [])


def _revision(metadata: Any) -> int:
    return int((metadata.annotations or {}).get(REVISION_ANNOTATION, 0))


@asynccontextmanager
async def _apps_api() -> AsyncIterator[client.AppsV1Api]:
    async with ApiClient(await _load_configuration()) as api_client:
        yield client.AppsV1Api(api_client)


async def _load_configuration() -> client.Configuration:
    global _configuration
    async with _configuration_lock:
        if _configuration is None:
            configuration = client.Configuration()
            if settings.kubernetes_in_cluster:
                config.load_incluster_config(client_configuration=configuration)
            else:
                await config.load_kube_config(client_configuration=configuration)
            _configuration = configuration
        return _configuration


async def _call(request: Any) -> Any:
    """Turns Kubernetes API failures into the app's errors."""
    try:
        return await request
    except ApiException as exc:
        if exc.status == 404:
            raise NotFoundError("Deployment not found") from exc
        if exc.status == 409:
            raise ConflictError("The deployment changed at the same time; try again") from exc
        # 403 included: it means the service account's RBAC doesn't allow this, a deployment problem.
        raise UpstreamError(f"Kubernetes API returned {exc.status}", details={"reason": exc.reason}) from exc
    except (ClientError, TimeoutError) as exc:
        raise UpstreamError("Kubernetes API is unreachable", details={"error": type(exc).__name__}) from exc
