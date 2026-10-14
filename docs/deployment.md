# Deployment

The copilot ships as two images and a set of Kubernetes manifests (`deploy/k8s`). A local [kind](https://kind.sigs.k8s.io) cluster runs the same images and manifests for trying it out.

## Images

| Image | Build | Runs |
|---|---|---|
| API | `docker build -t <registry>/rag-copilot-api:<tag> api` | `uvicorn` on port 8000. The same image runs the migration job (`alembic upgrade head`). Runtime dependencies only; runs as UID 1000 |
| Web | `docker build --target prod -t <registry>/rag-copilot-web:<tag> web` | nginx (unprivileged) on port 8080, serving the built UI and forwarding `/v1` to `API_UPSTREAM` (default `http://api:8000`) |

The browser only ever talks to the web origin, so the API needs no CORS setup and doesn't have to be exposed publicly.

## Kubernetes manifests

`deploy/k8s/base` is namespace-agnostic and contains:

- **api**: a Deployment (2 replicas) and Service, plus the `copilot-api` service account. Readiness is `/v1/health` (Postgres and Redis); liveness only checks that the port accepts connections, so a database outage doesn't restart pods. Shutdown waits up to 330 s, long enough for an approved remediation to finish verifying.
- **migrate**: a Job that applies migrations. Job templates can't be changed, so delete the old Job before applying a new image version. API pods that start before it finishes fail their startup checks and restart until it has run.
- **web**: a Deployment (2 replicas) and Service on port 80.

Containers run as non-root, with no privilege escalation and all capabilities dropped. The API's root filesystem is read-only.

An overlay for your environment adds:

1. **`copilot-config`**: a ConfigMap with the non-secret settings. The variable names are the same as in `api/.env.production.example`.
2. **`copilot-secrets`**: a Secret with `DATABASE_URL`, `AUTH_JWT_SECRET` and the LLM/embedding API keys. `deploy/k8s/secret.example.yaml` lists the keys; create the real one with your secret tooling, never from a committed file.
3. Postgres (with the pgvector extension available) and Redis, or managed equivalents.
4. **RBAC for the namespace the copilot may change**, when `DEPLOYMENT_BACKEND=kubernetes` (below).

## Letting the copilot act on Kubernetes

With `DEPLOYMENT_BACKEND=kubernetes`, a service name is the name of a Deployment in `KUBERNETES_NAMESPACE`. The API uses its pod's service account (`KUBERNETES_IN_CLUSTER=true`) or, when running outside a cluster, the local kubeconfig.

| Copilot action | What happens in Kubernetes |
|---|---|
| Read state | The Deployment and its ReplicaSets (rollout history) |
| `rollback_deployment` | The previous revision's pod template is put back, as `kubectl rollout undo` does |
| `restart_deployment` | A template annotation changes, so every pod is replaced, as `kubectl rollout restart` does |
| `scale_deployment` | `spec.replicas` is set |

It needs exactly this in the controlled namespace, and nothing anywhere else. `deploy/k8s/kind/payments/rbac.yaml` is the reference:

```yaml
rules:
  - apiGroups: [apps]
    resources: [deployments]
    verbs: [get, list, patch]
  - apiGroups: [apps]
    resources: [replicasets]
    verbs: [get, list]
```

Bind it to the `copilot-api` service account of the copilot's namespace with a RoleBinding in the controlled namespace. There's no create or delete, and no access to pods or secrets.

**Versions:** a revision's version is its pod template's `app.kubernetes.io/version` label. Without that label, the first container's image tag (or digest) is used. Set the label if tags don't say anything useful.

**Deploy times:** Kubernetes doesn't record when a revision went live. A new revision's time is exact: its ReplicaSet's creation. A rollback reuses an old ReplicaSet, so the current revision is dated by when its rollout last progressed. An older revision that came from a rollback shows "unknown time", and the copilot is told so rather than given a misleading time.

## Local cluster (kind)

`make k8s-tools` downloads pinned, checksum-verified `kind` and `kubectl` into `.tools/` (gitignored); nothing is installed system-wide.

```sh
make k8s-up        # create the cluster, build and load the images, apply everything, wait until ready
make k8s-verify    # RBAC, the Kubernetes deployment backend (from inside the API pod) and the web/API path
make k8s-ui        # the UI from the cluster at http://localhost:8090
make k8s-release v2  # a real rollout of the demo payments service to v2 (or v1)
make k8s-down      # delete the cluster
```

The cluster runs the copilot in the `copilot` namespace, with throwaway Postgres and Redis. The demo payments service runs in `payments`: changing its version is a real rollout, and the copilot may act on that namespace only. Monitoring queries go to the dev compose stack's LGTM container, which `make k8s-up` attaches to the kind network, so keep `make up` running for evidence. The LLM is an Ollama on the host. Create a superuser with `.tools/kubectl --context kind-rag-copilot -n copilot exec -it deploy/api -- python -m src.modules.auth.cli you@example.com`.

`make k8s-verify` checks that the copilot's service account may patch Deployments in `payments` but may not delete or create them, read pods or secrets, or touch any other namespace. From inside the API pod, it then reads a v2 release, rolls it back, restarts, and scales up and down, and confirms that other namespaces are refused.
