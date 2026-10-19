# Development

## Prerequisites

- Docker with Compose v2
- [uv](https://docs.astral.sh/uv/) and Node 24 (only for linting, formatting and browser tests on the host)
- A model provider. The defaults in `api/.env.local.example` use [Ollama](https://ollama.com) on the host:
  `ollama pull qwen3:8b && ollama pull nomic-embed-text`. Any LangChain-supported provider works; see [Configuration](#configuration).

## Running

```sh
make up        # first run copies the .env examples, builds, migrates, starts everything
make logs api  # follow logs of one service
make down      # stop
make clean     # stop and delete the database and telemetry volumes
```

| Service | URL |
|---|---|
| Web UI | http://localhost:5173 |
| API (OpenAPI docs at `/docs`) | http://localhost:8000 |
| Grafana (Loki, Tempo, Prometheus datasources preconfigured; **Copilot** and **Demo payments service** dashboards) | http://localhost:3000 |
| Demo payments service (admin API under `/admin/deployments/payments`) | http://localhost:8001 |

The `api` container bind-mounts `api/` and reloads on change. Its virtualenv lives in `/opt/venv` inside the image, so it isn't hidden by the mount; rebuild (`make up`) after changing dependencies.

## Everyday commands

| Command | What it does |
|---|---|
| `make metrics` | The copilot's runs, step latency, step errors and LLM token use, redrawn every 5 s in the terminal (the Copilot Grafana dashboard's queries). Pair it with `make logs api` |
| `make test` | Run pytest inside the api container. Tests use real Postgres and Redis, but a separate `<db>_test` database that is recreated from the migrations on every run, so dev data is never touched. Monitoring tests query the live stack and briefly deploy the demo service's `v2`, so the whole stack must be up; they take ~40 s |
| `make eval` | Score the copilot against a real LLM (see [Evaluating the copilot](#evaluating-the-copilot)) |
| `make seed` | Load example incidents (skipped if the table has rows) and ingest `api/seed/documents/*.md` (unchanged files are skipped). Ingesting needs the embedding provider to be running |
| `make demo-deploy v2` / `make demo-rollback` | Release the demo service's faulty `v2` / roll back to the previous version |
| `make createsuperuser admin@example.com` | Create a superuser (prompts for the password) |
| `make lint` / `make format` | Ruff, oxlint, Prettier and the TypeScript check / their auto-fixes, on the host |
| `make web-e2e` | Browser tests of the UI against the running stack (see [Web UI](#web-ui)) |
| `make web-types` | Regenerate the UI's API types after changing the API |
| `make revision m="add user table"` | Autogenerate an Alembic migration |
| `make migrate` | Apply migrations |
| `make psql`, `make redis-cli`, `make app_bash`, `make python` | Shells into the services |
| `make compose <args>` | Any other `docker compose` command against the dev stack |

Add dependencies with `cd api && uv add <package>` (`--dev` for tooling).

## Configuration

Two kinds of configuration:

- **Environment variables** — anything that differs per deployment: connection URLs, model provider/model, secrets. Read and validated by `Settings` in the API's core config. Examples: `api/.env.local.example` (works as-is for local dev) and `api/.env.production.example`.
- **`api/config/app.yaml`** — anything that is the same everywhere: service name, title, token lifetime, the monitoring query templates, and later the action/risk catalog. The version comes from `api/pyproject.toml`.

In dev, every URL that points at another container (`DATABASE_URL`, `REDIS_URL`, `PROMETHEUS_URL`, `LOKI_URL`, `TEMPO_URL`, `DEMO_PAYMENTS_ADMIN_URL`) is set by Compose, using the Postgres credentials in the root `.env`, so `api/.env` only holds your own choices (model provider, secrets).

### Choosing a model provider

The chat model and embeddings are created through LangChain's `init_chat_model` / `init_embeddings`, so switching provider is configuration only:

| Variable | Example (OpenAI) | Example (Anthropic chat) |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `anthropic` |
| `LLM_MODEL` | `gpt-5-mini` | `claude-sonnet-5-5` |
| `LLM_BASE_URL` | empty (or an OpenAI-compatible server URL) | empty |
| `LLM_API_KEY` | your key | your key |

Bundled integrations: `openai` (also any OpenAI-compatible server such as vLLM or LM Studio), `anthropic`, `ollama`. Others: `uv add langchain-<provider>`.

Embeddings are configured the same way with the `EMBEDDING_*` variables. `EMBEDDING_DIMENSIONS` must match the embedding model's output size; changing the embedding model later requires a migration and re-indexing.

### Running on a local Ollama

The defaults in `api/.env.local.example` already use Ollama on the host; set `LLM_MODEL` to any model from `ollama list`. Three things on the host decide whether it works:

- **Containers must reach Ollama.** They connect to `host.docker.internal:11434`, but Ollama listens on `127.0.0.1` only by default. Make it listen on all interfaces with `sudo systemctl edit ollama`, adding `[Service]` and `Environment="OLLAMA_HOST=0.0.0.0:11434"`, then `sudo systemctl restart ollama`. This also exposes it to your network, so firewall port 11434 if that matters. Check with `make app_bash` then `curl host.docker.internal:11434/api/tags`.
- **Enough context.** Many models default to a 4096-token context, and Ollama silently cuts longer prompts; a diagnose prompt with runbooks and evidence is about 3,000 tokens before the reply. Create a variant with more room and use its name as `LLM_MODEL`: `printf 'FROM <model>\nPARAMETER num_ctx 8192\n' > Modelfile && ollama create <model>-8k -f Modelfile`.
- **Enough memory.** On CPU the model is loaded into RAM (a 7B Q4 model needs about 4.5 GiB, plus some for the larger context) on top of about 2 GiB for the dev stack. If Ollama replies "model requires more system memory", free some up (e.g. `make k8s-down`) or pick a smaller model.

Structured output through Ollama uses its JSON-schema `format` rather than tool calls, so completion-only models (e.g. DeepSeek-R1 distills) work too. Small local models diagnose less reliably than hosted ones; `make eval model=<model>` measures how well.

To watch a run from the terminal, keep three terminals open: `make logs api` (the API's JSON logs: run status changes, monitoring queries, requests and errors; `GET /v1/copilot/runs/{id}/steps` has the full detail), `make metrics` (runs, latencies, token use), and `journalctl -u ollama -f` (each model call and how long it took).

## Demo service and monitoring

The copilot needs something to monitor, so the dev stack includes a stand-in `payments` service (`demo_payments/`) and a load generator sending it 5 requests per second. The service is instrumented with OpenTelemetry auto-instrumentation and sends metrics, logs and traces to the `lgtm` container (Grafana, Prometheus, Loki, Tempo).

It has two versions:

| Version | Behaviour |
|---|---|
| `v1` (default) | p99 latency ~0.1 s, ~0.5% errors ("card network declined request") |
| `v2` | Bad release: latency 0.6–1.8 s, ~8% errors, logs "ledger-db query timed out: connection pool exhausted" |

`make demo-deploy v2` creates the incident the copilot is built to diagnose; `make demo-rollback` fixes it. Restarting the container resets it to `v1`.

The API reads this data through fixed query templates in `api/config/app.yaml` (p99 latency, error ratio, request rate, error logs, slow traces). Service names are validated before being substituted, so a caller, including the LLM later, can't inject its own query. Deployment state comes from the backend selected by `DEPLOYMENT_BACKEND`; only `demo` exists so far.

Recent incidents are stored in Postgres and served by `GET /v1/incidents?service=&since=&limit=` (default: last 30 days). `make seed` loads example incidents, including a past payments latency spike that was fixed by a rollback.

## Knowledge base (runbooks)

Runbooks, postmortems and wiki pages are stored as Markdown, split into chunks and embedded into pgvector for search.

- **Adding documents:** `POST /v1/knowledge/documents` (superusers only) with `title`, `source_uri`, `doc_type` (`runbook`, `postmortem`, `wiki`), `service_tags` and Markdown `content`. `source_uri` identifies the document: posting the same URI again replaces it, or does nothing if nothing changed. Seed documents in `api/seed/documents/` use YAML front matter for the metadata and get `seed://<filename>` URIs.
- **Tagging:** `service_tags` lists the services a document applies to. A document with no tags applies to every service (e.g. the general rollback runbook).
- **Searching:** `GET /v1/knowledge/search?q=&service=&limit=` (any signed-in user) returns the most similar chunks with a cosine-similarity `score`. With `service`, only that service's documents and untagged ones are searched.
- **Chunking:** documents are split by heading, and long sections further (`knowledge.chunk_max_chars` in `api/config/app.yaml`). Each chunk starts with its heading path, e.g. `Payments latency spike > Diagnose > 2. Check recent deployments`, so it makes sense on its own.
- **Changing the embedding model:** vectors from different models can't be compared, so the API refuses to start if the configured embedding provider/model or `EMBEDDING_DIMENSIONS` doesn't match the stored vectors. To switch models: write a migration that resizes `document_chunk.embedding` if the dimension changes, empty the `document` table, and re-run `make seed` (plus re-post any documents you added through the API).

Tests use a fake embedder, so `make test` doesn't need a model server; `make seed` and real searches do.

## Asking the copilot

`POST /v1/copilot/runs` with `{"question": "..."}` runs the copilot and returns the run when it's done (this can take as long as the LLM needs; there's no streaming yet).

1. **classify** decides whether the question is an investigation of a service, a how-to question for the runbooks, or out of scope, and which service and time window it's about.
2. For an investigation, **retrieve_runbooks** and **gather_evidence** run in parallel. Evidence comes from Prometheus (p99 latency, error ratio, request rate), Loki (error logs), Tempo (slow traces), the deployment backend and the incident history. A source that fails is passed on as "unavailable" rather than failing the run.
3. **diagnose** asks the LLM for an answer, the likely cause, its confidence, supporting evidence, recommended actions and, optionally, **one proposed action** from the catalog.
4. **propose_remediation** validates that action and stores it. The run then **pauses** with status `awaiting_approval` (see [Remediation and approval](#remediation-and-approval)).

How-to questions go to **retrieve_documents** → **answer_knowledge** instead.

Everything is recorded: `GET /v1/copilot/runs/{id}/steps` lists each node, each query with its arguments and results, and each LLM call with the exact messages sent and what came back. `GET /v1/copilot/runs` lists runs, newest first. Users see their own runs; superusers see everyone's.

If the LLM can't be reached, the request fails with 502 and `details.run_id`; the run is kept with status `failed`.

The chat model comes from the `LLM_*` settings (see [Choosing a model provider](#choosing-a-model-provider)); it must support tool calling, which the API checks at startup. `LLM_CLASSIFIER_MODEL` can name a smaller model for the classify step. `copilot.llm_timeout_seconds` in `api/config/app.yaml` caps each LLM call.

Tests use a scripted chat model, so they check routing, evidence and prompts but not how well a real model reasons. Try a real model by starting it (e.g. `ollama pull qwen3:8b`), running `make seed`, `make demo-deploy v2`, waiting a minute, and asking "Why is the payments service showing a latency spike?".

## Remediation and approval

The copilot can act, but never on its own say-so.

**The catalog** (`remediation.actions` in `api/config/app.yaml`) lists everything it can do and how risky each action is:

| Action | Risk | Effect |
|---|---|---|
| `rollback_deployment` | high | Re-deploy the previous version |
| `restart_deployment` | high | Restart every instance |
| `scale_deployment` | low | Set the replica count (1 to `max_replicas`) |

The LLM can only pick from this list. Risk comes from the catalog, and the target is always the service being investigated. An invalid proposal (e.g. 50 replicas) is dropped and recorded in the run's steps.

**Who may decide** (`ApprovalPolicy`):

| | Low risk | High risk |
|---|---|---|
| Approve | any active user | a superuser, but not on a run they started, unless they are the only active superuser |
| Reject | anyone who may approve, plus whoever started the run | same |

**Endpoints:** `GET /v1/remediations?status=proposed` is the approval queue: superusers see everything, other users see their own runs' proposals plus everyone's low-risk ones. Then `POST /v1/remediations/{id}/approve` or `/reject`, with an optional `{"comment": "..."}`.

**After approval** the API answers `202` right away. The paused run resumes in the background: **execute_action** carries out the action exactly once, then **verify_outcome** checks the service's metrics every `poll_seconds` until every threshold in `remediation.verification.thresholds` holds (p99 ≤ 0.3 s, error ratio ≤ 1%), or `timeout_seconds` passes. Poll `GET /v1/remediations/{id}` or the run for the outcome:

| Proposal status | Meaning |
|---|---|
| `proposed` | Waiting for a decision |
| `rejected` | Turned down; nothing was done; the run's status is `rejected` |
| `executing` | Approved and being carried out or verified |
| `verified` | Done, and the service recovered |
| `unverified` | Done, but the metrics didn't recover in time: escalate |
| `failed` | The action itself failed, or the run broke after approval (the reason is in `execution.error`) |

Paused runs are saved by LangGraph's Postgres checkpointer, so they survive API restarts. The checkpointer creates its own `checkpoint*` tables; Alembic ignores them.

Known limit: the action and its verification run as an in-process background task. A graceful shutdown waits for it to finish, but if the API process crashes during those minutes, that work stops. The run then stays `running` and the proposal stays `executing`, and you have to check the service yourself.

## Observing the copilot

The API sends its own traces, metrics and logs over OTLP to the same LGTM stack it monitors. This is on by default in dev; set `TELEMETRY_TRACES_ENABLED=false` in the root `.env` to turn it off. When it's on, `OTEL_EXPORTER_OTLP_ENDPOINT` is required.

- **Traces (Tempo):** every HTTP request, database query and outgoing HTTP call (monitoring stack, deployment backend, LLM providers) is traced automatically. Each copilot run is one trace, `copilot.run`, with a child span per graph node, evidence query and LLM call. LLM spans carry `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` when the provider reports them. The work after an approval is its own trace, `copilot.resume`.
- **Audit trail ↔ traces:** every row from `GET /v1/copilot/runs/{id}/steps` has a `trace_id`. Paste it into Grafana's Explore → Tempo to see timings next to the step's recorded inputs and outputs.
- **Logs:** stdout JSON logs include `trace_id` and `span_id`. The same logs go to Loki (`{service_name="rag-copilot-api"}`), where Grafana links them to their traces.
- **Metrics (Prometheus):**

| Metric | Labels | Meaning |
|---|---|---|
| `copilot_runs_total` | `status` | Runs reaching awaiting_approval, completed, rejected or failed |
| `copilot_step_duration_milliseconds` | `node`, `tool`, `error` | Every node (`tool` empty), evidence query and LLM call (`tool="llm"`) |
| `copilot_llm_tokens_total` | `node`, `type`, `model` | Input/output tokens, when the provider reports them |
| `copilot_remediation_events_total` | `event`, `action`, `risk` | proposed, approved, rejected, verified, unverified, failed |

The **Copilot** dashboard shows runs by outcome, remediation events, step errors, p95 latency per node and per LLM call, tokens per minute, recent run traces, and warning/error logs. Metrics are exported every 10 s; rate panels need two exports before they show anything.

Tests don't export anything: they install in-memory providers and assert on the spans and metrics a run produces.

## Evaluating the copilot

Tests prove the plumbing works; evals measure whether a real model makes the right calls. `make eval` runs the cases in `api/evals/datasets/copilot.yaml` against the configured LLM and prints a pass/fail line per case:

```sh
make eval                                   # LLM_PROVIDER / LLM_MODEL from api/.env
make eval model=qwen3:14b                   # another model from the same provider
make eval provider=openai model=gpt-5-mini  # another provider; its SDK reads its own key, e.g. OPENAI_API_KEY
make eval case=prompt-injection-in-logs     # one case
```

It exits non-zero below the dataset's `min_pass_rate` (80%). A JSON report with every answer is written to `api/evals/reports/`, which is gitignored. That's the way to compare models: same cases, same evidence, only the LLM changes.

**What a case checks** (all optional): the classifier's category and service; which evidence queries ran; words the answer must contain (each group needs at least one); and the proposed action, or `none`. A proposed action must also leave the run waiting for approval.

**Reproducible evidence:** cases name a *scenario*, a recorded snapshot of what the monitoring stack and deployment backend returned (`api/evals/fixtures/*.json`). Replay shifts its timestamps to "now", so evals give the same picture whenever they run and never touch the live stack or the demo service. Runbooks and incidents are the seed data. Evals use their own `<db>_eval` database, recreated each run, and need the embedding provider for retrieval.

| Scenario | How it was made |
|---|---|
| `healthy` | Recorded: demo v1, no deployment in the window |
| `bad_release` | Recorded: v2 deployed 3 minutes earlier (latency spike, pool-exhaustion errors) |
| `card_network` | `healthy` with ~3% card-network declines written in |
| `injected_logs` | `bad_release` plus a log line telling the AI to scale instead of rolling back |

To re-record after changing the demo service or the queries: `make compose restart payments`, then `make eval-record` (~15 min; it deploys v2 for a few minutes and then v1 again).

The harness is tested too (`make test`), with scripted models: one that answers exactly as the dataset expects must pass every case, and one that knows nothing must fail the right checks.

## Web UI

`web/` is a React app (Vite, TypeScript, Tailwind) served by the `web` container at http://localhost:5173, with hot reload. Sign in with any user. The first superuser comes from `make createsuperuser`.

| Page | What it's for |
|---|---|
| Ask | Ask a question; you land on the run when it's done |
| Run | The answer (rendered Markdown), the diagnosis, any proposed action with Approve/Reject, and every step the copilot took, expandable to its exact inputs and outputs |
| Runs | History, newest first (superusers see everyone's) |
| Approvals | Proposals waiting for a decision; the count also shows in the nav bar |
| Users | Superusers only: add users, deactivate them, reset passwords |

The UI calls the API on its own origin (`/v1/...`), and Vite forwards those requests to the `api` container, so no CORS is needed. Pages poll while something is in progress, such as a run or an approved action being verified.

- **API types** in `web/src/api/schema.d.ts` are generated from the API's OpenAPI spec. After changing an endpoint or schema, run `make web-types` and commit the result. `make lint` then type-checks the UI against the new API.
- **Design tokens** (colours for surfaces, text and statuses) are defined once in `web/src/index.css`. Components use the token names (`bg-surface`, `text-danger`, ...), never raw palette colours.
- **Browser tests:** `make web-e2e` runs Playwright in your installed Chrome against the running stack. It first creates two users and four runs in the dev database with the scripted LLM, tagged with a random suffix. It then signs in, browses runs, is refused approval of its own high-risk action, rejects it, approves a low-risk scale from the queue and waits for it to be verified (this really scales the demo service, and the teardown puts it back), and adds a user. Test data stays in the dev database; `make clean` removes it.

## Kubernetes

Production images, the Kubernetes manifests, the Kubernetes deployment backend and a local kind cluster are described in [Deployment](deployment.md).

## Users and authentication

- There is no sign-up. Create the first superuser with `make createsuperuser <email>`; superusers then create regular users through `POST /v1/users`. Superusers can only be created through the CLI.
- Log in with `POST /v1/auth/token` (`{"email", "password"}`) and send the returned token as `Authorization: Bearer <token>`. In the OpenAPI docs, use the **Authorize** button.
- Tokens are JWTs signed with `AUTH_JWT_SECRET` and expire after `auth.access_token_ttl_minutes` (in `api/config/app.yaml`). Changing the secret logs everyone out.
- The account is re-checked on every request: deactivating a user (`PATCH /v1/users/{id}` with `{"is_active": false}`) cuts off their existing tokens immediately, and a password reset revokes all tokens issued before it.
- Emails are case-insensitive; passwords must be 12–128 characters.
- Protected routes take the `CurrentUser` dependency, which also sets `request.state.user`. Permission rules live in policy classes (e.g. `UserPolicy`) and are checked in services.

## API conventions

- Every public route is under `/v1`.
- Errors always have the shape `{"error": {"code", "message", "details"}}`. Raise an `AppError` subclass anywhere; the global handlers log it and render the response. Don't catch-and-log or build error responses by hand.
- Logs are JSON on stdout. Use the shared app logger and pass context with `extra={...}`; every request is logged with method, path, status and duration. `LOG_LEVEL` controls the app's own logs only.
- `GET /v1/health` returns 200 when Postgres and Redis respond, otherwise 503 with the failing checks in `details`. It needs no authentication; every other route except `POST /v1/auth/token` does.
