# Development

## Prerequisites

- Docker with Compose v2
- [uv](https://docs.astral.sh/uv/) (only for linting/formatting on the host)
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
| API (OpenAPI docs at `/docs`) | http://localhost:8000 |
| Grafana (Loki, Tempo, Prometheus datasources preconfigured; **Demo payments service** dashboard) | http://localhost:3000 |
| Demo payments service (admin API under `/admin/deployments/payments`) | http://localhost:8001 |

The `api` container bind-mounts `api/` and reloads on change. Its virtualenv lives in `/opt/venv` inside the image, so it isn't hidden by the mount; rebuild (`make up`) after changing dependencies.

## Everyday commands

| Command | What it does |
|---|---|
| `make test` | Run pytest inside the api container. Tests use real Postgres and Redis, but a separate `<db>_test` database that is recreated from the migrations on every run, so dev data is never touched. Monitoring tests query the live stack and briefly deploy the demo service's `v2`, so the whole stack must be up; they take ~40 s |
| `make seed` | Load example data (incidents); does nothing if the table already has rows |
| `make demo-deploy v2` / `make demo-rollback` | Release the demo service's faulty `v2` / roll back to the previous version |
| `make createsuperuser admin@example.com` | Create a superuser (prompts for the password) |
| `make lint` / `make format` | Ruff check + format check / auto-fix + format, on the host |
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
