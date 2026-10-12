DEV_COMPOSE = docker compose --env-file .env -f docker-compose.dev.yaml

# Everything after the first Make goal is treated as positional arguments.
ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))

.PHONY: prepare-env compose up up-f down clean logs migrate revision test lint format createsuperuser seed demo-deploy demo-rollback psql redis-cli app_bash python

# Create local configuration once while preserving every developer override.
prepare-env:
	@test -f .env || cp .env.local.example .env
	@test -f api/.env || cp api/.env.local.example api/.env

compose:
	$(DEV_COMPOSE) $(ARGS)

up: prepare-env
	$(DEV_COMPOSE) up -d --build --remove-orphans $(ARGS)

up-f: prepare-env
	$(DEV_COMPOSE) up --build --remove-orphans $(ARGS)

down:
	$(DEV_COMPOSE) down --remove-orphans $(ARGS)

# Also deletes the Postgres and telemetry volumes.
clean:
	$(DEV_COMPOSE) down --remove-orphans --volumes $(ARGS)

logs:
	$(DEV_COMPOSE) logs --follow $(ARGS)

migrate:
	$(DEV_COMPOSE) run --rm migrate $(ARGS)

revision:
	$(DEV_COMPOSE) exec api alembic revision --autogenerate -m "$(m)"

# Tests need Postgres and Redis, so they run inside the api container.
test:
	$(DEV_COMPOSE) exec api pytest $(ARGS)

lint:
	cd api && uv run ruff check . && uv run ruff format --check .

format:
	cd api && uv run ruff check --fix . && uv run ruff format .

# Usage: make createsuperuser admin@example.com (prompts for the password).
createsuperuser:
	$(DEV_COMPOSE) exec api python -m src.modules.auth.cli $(ARGS)

# Load example data (currently incidents); safe to re-run.
seed:
	$(DEV_COMPOSE) exec api python -m src.modules.incidents.seed

# Usage: make demo-deploy v2 (v2 causes a latency spike and errors; see demo_payments/app.py).
demo-deploy:
	curl -sf -X POST localhost:8001/admin/deployments/payments/deploy -H 'content-type: application/json' -d '{"version": "$(ARGS)"}'; echo

demo-rollback:
	curl -sf -X POST localhost:8001/admin/deployments/payments/rollback; echo

psql:
	$(DEV_COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' $(ARGS)

redis-cli:
	$(DEV_COMPOSE) exec redis redis-cli $(ARGS)

app_bash:
	$(DEV_COMPOSE) exec api bash $(ARGS)

python:
	$(DEV_COMPOSE) exec api python $(ARGS)

# Accept positional arguments as Make goals.
%:
	@:
