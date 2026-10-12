# Enterprise AI Operations Copilot — Implementation Plan

## 1. Goal

An API-first copilot, with a minimal React UI, that answers operational questions ("Why is the payments service showing a latency spike?") by:

1. classifying the request,
2. retrieving runbooks/internal docs (RAG over pgvector),
3. gathering evidence from monitoring (metrics, logs, traces, deployment state, recent incidents),
4. summarizing evidence and proposing a likely cause and remediation,
5. pausing for human approval on high-risk actions,
6. executing approved actions through typed tools,
7. verifying the outcome,
8. tracing every step, and
9. being regression-tested by an evaluation dataset.

## 2. Current state

- `uv init` skeleton only (`main.py`, empty `README.md`, `pyproject.toml` with no deps, Python 3.14).
- AGENTS.md is the only source of project rules.

## 3. Decisions

| Topic                | Decision                                                                                                                                                                                                                                                                                                                  | Why                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Python               | Latest stable: **3.14** (3.14.5 at time of writing; 3.15 is still beta). `python:3.14-slim` base image                                                                                                                                                                                                                    | User requirement; bump when 3.15 is final and deps ship wheels                    |
| API                  | FastAPI, every route under `/v1`                                                                                                                                                                                                                                                                                          | Project override                                                                  |
| LLM                  | **Model-agnostic.** LangChain `init_chat_model(model, model_provider=...)` with provider/model from env. Bundled integrations: `langchain-openai` (also covers any OpenAI-compatible server: vLLM, LM Studio, LiteLLM), `langchain-anthropic`, `langchain-ollama`; more can be added with `uv add`                        | User requirement; one factory, no per-provider code paths                         |
| Embeddings           | Same approach via `init_embeddings` (`EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`)                                                                                                                                                                                                                                             | Same reason                                                                       |
| Provider requirement | Chat model must support tool calling / structured output (used for classification and tool selection). Checked at startup                                                                                                                                                                                                 | Fail fast instead of mid-run                                                      |
| Orchestration        | LangGraph `StateGraph` with `interrupt()` for approvals                                                                                                                                                                                                                                                                   | Built-in human-in-the-loop with resumable state                                   |
| Graph persistence    | `langgraph-checkpoint-postgres` on the same Postgres                                                                                                                                                                                                                                                                      | Runs survive restarts while awaiting approval                                     |
| Vector store         | `pgvector` column on `document_chunk`, SQLAlchemy                                                                                                                                                                                                                                                                         | Single DB                                                                         |
| ORM / migrations     | SQLAlchemy 2 (async) + asyncpg + Alembic                                                                                                                                                                                                                                                                                  | One migration per table                                                           |
| Redis                | Execution lock (approved action runs once). A monitoring-query cache was considered and deferred until a real need shows up | Nothing else needs it yet                                                         |
| Monitoring stack     | Local **Grafana LGTM + Prometheus** via the single `grafana/otel-lgtm` image (Grafana, Loki, Tempo, Prometheus, OTel Collector)                                                                                                                                                                                           | User requirement; one container instead of five                                   |
| Monitoring adapters  | Prometheus HTTP API (PromQL), Loki (LogQL), Tempo (TraceQL)                                                                                                                                                                                                                                                               | Real queries against the local stack                                              |
| Something to monitor | A small **demo `payments` service** + load generator in compose, OTel-instrumented, with deployable "versions" (`v1` healthy, `v2` injects latency/errors)                                                                                                                                                                | Gives the copilot a real latency spike to diagnose and a real rollback to perform |
| Deployment adapter   | `DEPLOYMENT_BACKEND=demo` (talks to demo service's admin API: current/previous version, rollback) or `kubernetes` (K8s API: rollout history, `rollout undo`, scale, restart; built in Phase 9, where a cluster exists to verify it)                                                                                                                                              | Local loop works without a cluster; real backend for K8s deployments              |
| Own telemetry        | Copilot exports its own traces/metrics/logs to the same LGTM stack. Plus a persisted `run_step` audit trail in Postgres                                                                                                                                                                                                   | OTel for operators; DB trail is the record of who approved what                   |
| Auth                 | `user` table; **superusers created via CLI** (`make createsuperuser`, argparse + getpass, argon2 hashing via `pwdlib`); **regular users created by superusers via API**; `POST /v1/auth/token` issues JWT (`pyjwt`); the `get_current_user` dependency sets `request.state.user`                                                                 | User requirement; no self-registration                                            |
| Permissions          | Policy classes: `UserPolicy` (only superusers manage users), `ApprovalPolicy` (any active user approves `low` risk; only superusers approve `high`; nobody approves their own `high`-risk run unless they are the sole active superuser, who may do anything), `RunPolicy` (users see their own runs; superusers see all) | Separation of duties for risky actions                                            |
| Frontend             | After backend is done: **Vite + React + TypeScript + Tailwind**, API types generated from FastAPI's OpenAPI (`openapi-typescript`)                                                                                                                                                                                        | Minimal UI; single source of truth for API types                                  |
| Lint/format          | `ruff check` + `ruff format` (api), `eslint` + `prettier` (web)                                                                                                                                                                                                                                                           | No formatter configured yet                                                       |
| Tests                | `pytest` + `pytest-asyncio` + `httpx.AsyncClient`, real Postgres in compose; fake adapters/LLM only in tests                                                                                                                                                                                                              | Test API behaviour + DB effects                                                   |

## 4. Repository layout

Monorepo so the React app slots in later without moving the backend. Backend is module-first with onion dependencies inside each module: router → controller → service → query/repository/adapters. Domain modules never import FastAPI.

```
rag-copilot/
├── Makefile
├── docker-compose.dev.yaml         # api, migrate, postgres(pgvector), redis, lgtm, demo-payments, loadgen, (web)
├── .env.local.example                            # dev compose vars (Postgres credentials)
├── config/
│   └── grafana/                    # provisioned dashboards
├── deploy/k8s/                     # api Deployment/Service, migrate Job, ConfigMap, Secret template, RBAC
├── docs/
├── api/
│   ├── Dockerfile                  # venv at /opt/venv
│   ├── pyproject.toml, uv.lock, alembic/
│   ├── .env.local.example / .env.production.example
│   ├── config/app.yaml             # service name, version, top_k, action/risk catalog, verification defaults
│   ├── seed/documents/*.md, seed/incidents.yaml
│   ├── evals/datasets/*.yaml, evals/fixtures/, evals/run_evals.py
│   ├── src/
│   │   ├── main.py                 # app factory, mounts /v1 routers
│   │   ├── core/
│   │   │   ├── config.py           # pydantic-settings, conditional validation
│   │   │   ├── logging.py          # global logger (JSON, trace_id injected)
│   │   │   ├── telemetry.py
│   │   │   ├── database.py, redis.py
│   │   │   ├── llm.py              # chat model + embeddings factory from env
│   │   │   ├── exceptions.py       # AppError hierarchy
│   │   │   ├── exception_handlers.py  # global: log + uniform JSON response
│   │   │   └── dependencies.py     # get_session, get_redis
│   │   └── modules/
│   │       ├── auth/               # user model, token endpoint, CLI, policies
│   │       ├── knowledge/          # documents, chunking, embedding, retrieval
│   │       ├── monitoring/         # Prometheus / Loki / Tempo adapters
│   │       ├── deployments/        # demo + kubernetes adapters
│   │       ├── incidents/
│   │       ├── copilot/            # LangGraph graph, classifier, runs API
│   │       ├── remediation/        # action catalog, proposals, approvals, execution, verification
│   │       └── audit/              # run_step persistence
│   └── tests/
├── demo_payments/                  # tiny FastAPI service + loadgen script (dev only)
└── web/                            # React app (Phase 8)
```

Each module uses only the files it needs from:
`<x>_router.py`, `<x>_controller.py`, `<x>_service.py`, `<x>_query.py` (reads), `<x>_repository.py` (writes, no commits, no DTOs), `models.py` (ORM), `schemas.py` (DTOs), `<x>_policy.py`.

## 5. Data model (initial)

| Table                  | Key columns                                                                                                             | Notes                                                                                              |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `app_user`             | id, email, password_hash, is_superuser, is_active, token_version, created_by_id, created_at                             | Superusers via CLI; regular users via API. Deactivate, never delete (audit trail references users). Not `user`: reserved word in Postgres |
| `document`             | id, title, source_uri, doc_type (runbook/postmortem/wiki), service_tags[], content_hash, created_at, updated_at         | `source_uri` is the identity (re-ingesting replaces the document); `content_hash` makes unchanged re-ingestion a no-op |
| `document_chunk`       | id, document_id, chunk_index, content, embedding vector(N), embedding_model                                             | HNSW index; N = `EMBEDDING_DIMENSIONS` when the migration ran. Service filter joins `document` (no copied tags) |
| `incident`             | id, service, severity, title, summary, status, started_at, resolved_at                                                  | Seeded in dev                                                                                      |
| `copilot_run`          | id, user_id, question, classification, status (running/awaiting_approval/completed/failed/rejected), answer, created_at | One per question                                                                                   |
| `run_step`             | id, run_id, node, tool_name, input_json, output_json, duration_ms, trace_id, created_at                                 | Audit trail; secrets redacted                                                                      |
| `remediation_proposal` | id, run_id, action_type, params_json, risk_level, rationale, status                                                     | proposed/approved/rejected/executed/failed/verified                                                |
| `approval`             | id, proposal_id, approver_id, decision, comment, decided_at                                                             |                                                                                                    |
| `action_execution`     | id, proposal_id, started_at, finished_at, result_json, verification_json                                                |                                                                                                    |

UUIDs generated by Postgres (`gen_random_uuid()`). LangGraph checkpoint tables are managed by its own `setup()`.

**Embedding dimension caveat:** the vector column's size is set from `EMBEDDING_DIMENSIONS` when the migration first runs. The API refuses to start if `EMBEDDING_DIMENSIONS` or the embedding provider/model no longer match what's stored. Switching embedding model means a migration that resizes the column plus re-ingesting every document; switching chat model needs nothing.

## 6. Agent graph

```
classify ──► (knowledge_question) ──► retrieve ──► answer ──► END
   │
   └──► (diagnosis / status / remediation_request)
         retrieve_runbooks
           ▼
         gather_evidence   (Prometheus, Loki, Tempo, deployments, incidents — in parallel)
           ▼
         summarize_evidence
           ▼
         hypothesize_cause
           ▼
         propose_remediation ──► (no action / read-only) ──► END
           ▼ (low or high risk)
         await_approval   (interrupt(); run.status = awaiting_approval; who may approve per ApprovalPolicy)
           ▼ approved                       ▼ rejected
         execute_action                    END
           ▼
         verify_outcome   (re-query PromQL vs. runbook threshold after a settle delay)
           ▼
         END
```

- Classification is structured output (`category`, `service`, `time_window`); `out_of_scope` short-circuits.
- One decorator wraps every node: writes a `run_step` row and opens an OTel span.
- Tools are typed (Pydantic input/output) and declared in `config/app.yaml` with `risk_level` (`read`, `low`, `high`). Executing `high` without an approved `approval` raises `ForbiddenError` in `RemediationService`. The graph is not the only gate.
- PromQL/LogQL are built from templates per tool (e.g. `latency_p99(service, window)`), not free-form LLM queries. That keeps queries valid and bounded.
- MVP actions: `rollback_deployment` (high), `restart_deployment` (high), `scale_deployment` (low).
- Execution takes a Redis lock keyed by proposal id, so a double-clicked approval executes once.

## 7. API surface (`/v1`)

| Method | Path                               | Purpose                                              |
| ------ | ---------------------------------- | ---------------------------------------------------- |
| GET    | `/v1/health`                       | Liveness/readiness (DB, Redis). Monitoring is deliberately not a readiness check: an LGTM outage shouldn't take login and approvals down; it surfaces as 502 on monitoring queries |
| POST   | `/v1/auth/token`                   | Email/password → JWT                                 |
| GET    | `/v1/auth/me`                      | Current user                                         |
| POST   | `/v1/users`                        | Create regular user (superuser only)                 |
| GET    | `/v1/users`                        | List users (superuser only)                          |
| PATCH  | `/v1/users/{id}`                   | Activate/deactivate, reset password (superuser only) |
| POST   | `/v1/copilot/runs`                 | Ask a question (sync MVP; SSE later)                 |
| GET    | `/v1/copilot/runs`                 | List runs (for UI)                                   |
| GET    | `/v1/copilot/runs/{id}`            | Status, answer, evidence, proposals                  |
| GET    | `/v1/copilot/runs/{id}/steps`      | Audit trail                                          |
| GET    | `/v1/remediations?status=proposed` | Pending approvals (for UI)                           |
| POST   | `/v1/remediations/{id}/approve`    | Approve (policy-checked); resumes graph              |
| POST   | `/v1/remediations/{id}/reject`     | Reject; resumes graph to END                         |
| POST   | `/v1/knowledge/documents`          | Ingest a document                                    |
| GET    | `/v1/knowledge/search?q=`          | Debug retrieval                                      |
| GET    | `/v1/incidents?service=&since=`    | Recent incidents                                     |

## 8. Configuration

`api/config/app.yaml`: service name, version, retrieval top_k, action/risk catalog, PromQL/LogQL templates, verification defaults.

`api/.env.local.example` (grouped, secrets last):

```
# Database / cache
DATABASE_URL=
REDIS_URL=

# LLM — any LangChain-supported provider (openai, anthropic, ollama, …)
LLM_PROVIDER=
LLM_MODEL=
LLM_CLASSIFIER_MODEL=        # optional, defaults to LLM_MODEL
LLM_BASE_URL=                # optional, for OpenAI-compatible / self-hosted servers

# Embeddings
EMBEDDING_PROVIDER=
EMBEDDING_MODEL=
EMBEDDING_DIMENSIONS=
EMBEDDING_BASE_URL=          # optional, for self-hosted servers

# Monitoring stack (local LGTM)
PROMETHEUS_URL=
LOKI_URL=
TEMPO_URL=

# Deployment control: demo | kubernetes
DEPLOYMENT_BACKEND=
DEMO_PAYMENTS_ADMIN_URL=     # required when DEPLOYMENT_BACKEND=demo
KUBERNETES_IN_CLUSTER=       # required when DEPLOYMENT_BACKEND=kubernetes
KUBERNETES_NAMESPACE=        # required when DEPLOYMENT_BACKEND=kubernetes

# Own telemetry
TELEMETRY_TRACES_ENABLED=
OTEL_EXPORTER_OTLP_ENDPOINT= # required when TELEMETRY_TRACES_ENABLED=true

# Secrets
LLM_API_KEY=                 # optional for keyless providers (e.g. ollama)
EMBEDDING_API_KEY=
AUTH_JWT_SECRET=
```

Conditional requirements are enforced by a Pydantic `model_validator` in `core/config.py`.

## 9. Delivery phases

Each phase ends runnable, with tests, lint and docs updated.

**Phase 0 — Foundations**

- Move skeleton into `api/`, delete `main.py`.
- `uv add` deps; first confirm all deps (LangChain, LangGraph, asyncpg, pgvector, otel) install on 3.14.
- `core/` (config, logging, exception handlers, database, redis, llm factory), app factory, `/v1/health`.
- Dockerfile (`/opt/venv`), compose (postgres+pgvector, redis, api, migrate, lgtm), Makefile based on the AGENTS.md example, env examples, Alembic, ruff, pytest.

**Phase 1 — Auth**

- `user` table, `make createsuperuser` CLI, token endpoint, auth middleware, user management endpoints, `UserPolicy`.
- Tests: CLI-created superuser can log in and create a regular user; regular user cannot manage users; deactivated user cannot log in; anonymous requests rejected.

**Phase 2 — Knowledge / RAG**

- `document`, `document_chunk`; heading-aware markdown chunker; ingestion service (idempotent); vector search with service-tag filter; `make seed` ingests runbooks.
- Tests: ingest → search returns the expected runbook. They use a deterministic word-hashing fake embedder, so they test the pipeline (chunking, storage, ranking, filters); retrieval quality with real models belongs to the Phase 7 evals.

**Phase 3 — Demo service + monitoring + incidents**

- `demo_payments` service (OTel-instrumented, versions v1/v2, admin API) + loadgen in compose; Grafana dashboard for it.
- Prometheus/Loki/Tempo adapters with query templates in `config/app.yaml`; `demo` deployments adapter (read-only; rollback/scale/restart come with Phase 5); `incident` table + `make seed` + `GET /v1/incidents`.
- Tests run against the live stack: deploying `v2` must show up in deployment state, p99 latency, error ratio, error logs and slow traces.

**Phase 4 — Copilot graph (read-only)**

- Classifier, retrieval, parallel evidence, summarize, hypothesize, answer; `copilot_run`, `run_step`; node-tracing decorator; runs API.
- End-to-end check: deploy `v2` → ask the payments question → answer cites latency + the v2 deploy.

**Phase 5 — Remediation + approval**

- Action catalog; proposal/approval/execution tables; `interrupt()`/resume via Postgres checkpointer; approve/reject endpoints; Redis execution lock; verification node.
- `ApprovalPolicy`, `RunPolicy`.
- Tests: high-risk action cannot run without superuser approval; regular user can approve low-risk but not high-risk; superuser cannot approve their own high-risk run while another active superuser exists, but a sole active superuser can; approve → runs once → verified; reject → no execution.

**Phase 6 — Observability of the copilot**

- OTel instrumentation (FastAPI, SQLAlchemy, httpx, LangChain), trace_id in logs and `run_step`; Grafana dashboard: runs, per-node latency, token usage, approvals, tool errors.

**Phase 7 — Evaluation**

- Dataset rows: question, scenario, expected classification, required tools, expected cause keywords, expected action, approval required.
- Monitoring/deployment responses replayed from `evals/fixtures/` (recorded from the local stack by a script), so results don't depend on live traffic. Only the LLM varies, which is what we're evaluating.
- `make eval [provider/model overrides]` → pass-rate report, non-zero exit below threshold. This is also how providers/models are compared.

**Phase 8 — Web UI (after backend is complete)**

- Vite + React + TS + Tailwind in `web/`, generated API types, served in compose.
- Screens: login; ask a question + run view (step timeline, evidence, answer, proposed action); approvals queue with approve/reject; run history; user management (superusers only).

**Phase 9 — Kubernetes**

- Manifests for api, web, migrate Job, ConfigMap, Secret template; RBAC limited to the deployments/namespace the copilot may roll back/scale/restart.
- `kubernetes` deployment adapter (`DEPLOYMENT_BACKEND=kubernetes`), verified against a local kind cluster.

**Later**

- SSE streaming of run progress, hybrid (BM25 + vector) retrieval if evals show misses, external incident source.

## 10. Risks

- **Model-agnostic quality variance** — smaller/local models may fail at structured output or reasoning; startup capability check + evals per model make this visible.
- **Python 3.14 wheels** — verified in Phase 0: every planned dependency installs from wheels on 3.14.
- **Prompt injection via logs/docs** — retrieved content is treated as data; actions only via typed tools, server-side risk enforcement and superuser approval.
- **Over-privileged executor** — K8s RBAC scoped per namespace; executor credentials separate from read-only monitoring access.
