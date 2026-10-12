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
make clean     # stop and delete the database volume
```

| Service | URL |
|---|---|
| API (OpenAPI docs at `/docs`) | http://localhost:8000 |
| Grafana (Loki, Tempo, Prometheus datasources preconfigured) | http://localhost:3000 |

The `api` container bind-mounts `api/` and reloads on change. Its virtualenv lives in `/opt/venv` inside the image, so it isn't hidden by the mount; rebuild (`make up`) after changing dependencies.

## Everyday commands

| Command | What it does |
|---|---|
| `make test` | Run pytest inside the api container (tests use the real Postgres and Redis) |
| `make lint` / `make format` | Ruff check + format check / auto-fix + format, on the host |
| `make revision m="add user table"` | Autogenerate an Alembic migration |
| `make migrate` | Apply migrations |
| `make psql`, `make redis-cli`, `make app_bash`, `make python` | Shells into the services |
| `make compose <args>` | Any other `docker compose` command against the dev stack |

Add dependencies with `cd api && uv add <package>` (`--dev` for tooling).

## Configuration

Two kinds of configuration:

- **Environment variables** — anything that differs per deployment: connection URLs, model provider/model, secrets. Read and validated by `Settings` in the API's core config. Examples: `api/.env.local.example` (works as-is for local dev) and `api/.env.production.example`.
- **`api/config/app.yaml`** — anything that is the same everywhere: service name, title, and later the action/risk catalog and query templates. The version comes from `api/pyproject.toml`.

In dev, `DATABASE_URL` and `REDIS_URL` are built by Compose from the Postgres credentials in the root `.env`, so credentials live in one place.

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

## API conventions

- Every public route is under `/v1`.
- Errors always have the shape `{"error": {"code", "message", "details"}}`. Raise an `AppError` subclass anywhere; the global handlers log it and render the response. Don't catch-and-log or build error responses by hand.
- Logs are JSON on stdout. Use the shared app logger and pass context with `extra={...}`; every request is logged with method, path, status and duration. `LOG_LEVEL` controls the app's own logs only.
- `GET /v1/health` returns 200 when Postgres and Redis respond, otherwise 503 with the failing checks in `details`.
