DEV_COMPOSE = docker compose --env-file .env -f docker-compose.dev.yaml

# Everything after the first Make goal is treated as positional arguments.
ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))

.PHONY: k8s-tools k8s-up k8s-release k8s-verify k8s-ui k8s-down prepare-env compose up up-f down clean logs metrics migrate revision test lint format createsuperuser eval eval-record seed web-install web-types web-e2e demo-deploy demo-rollback psql redis-cli app_bash python

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

# The copilot's runs, step latency and LLM token use from Prometheus, redrawn every 5 s (Ctrl-C to stop).
metrics:
	$(DEV_COMPOSE) exec api python -m src.modules.copilot.metrics_cli

migrate:
	$(DEV_COMPOSE) run --rm migrate $(ARGS)

revision:
	$(DEV_COMPOSE) exec api alembic revision --autogenerate -m "$(m)"

# Tests need Postgres and Redis, so they run inside the api container.
test:
	$(DEV_COMPOSE) exec api pytest $(ARGS)

lint: web-install
	cd api && uv run ruff check . && uv run ruff format --check .
	cd web && npm run lint && npm run typecheck

format: web-install
	cd api && uv run ruff check --fix . && uv run ruff format .
	cd web && npm run format

# The web app's tooling (lint, types, browser tests) runs on the host; the dev server runs in its container.
web-install:
	@test -d web/node_modules || (cd web && npm ci)

# Regenerate the UI's API types from the running API; commit the result with the API change.
web-types:
	cd web && npx --yes openapi-typescript@7.13.0 http://localhost:8000/openapi.json -o src/api/schema.d.ts

# Browser tests against the running dev stack, in the installed Chrome. Adds tagged e2e users and runs to the dev
# database, and briefly scales the demo payments service.
web-e2e: web-install
	cd web && npx playwright test $(ARGS)

# Usage: make createsuperuser admin@example.com (prompts for the password).
createsuperuser:
	$(DEV_COMPOSE) exec api python -m src.modules.auth.cli $(ARGS)

# Score the copilot against a real LLM. Usage: make eval [provider=openai] [model=gpt-5-mini] [case=healthy-service]
eval:
	$(DEV_COMPOSE) exec api python -m evals.run_evals $(if $(provider),--provider $(provider)) $(if $(model),--model $(model)) $(if $(case),--case $(case))

# Re-record the evals' evidence fixtures from the live stack (~15 min; restart the payments container first).
eval-record:
	$(DEV_COMPOSE) exec api python -m evals.record_fixtures

# Load example incidents and documents (documents need the embedding provider); safe to re-run.
seed:
	$(DEV_COMPOSE) exec api python -m src.modules.incidents.seed
	$(DEV_COMPOSE) exec api python -m src.modules.knowledge.seed

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

# Pinned Kubernetes tooling, downloaded into .tools/ (gitignored) and checksum-verified; nothing is installed system-wide.
KIND_VERSION = v0.33.0
KUBECTL_VERSION = v1.37.1
TOOLS = $(CURDIR)/.tools
KIND = $(TOOLS)/kind
KUBECTL = $(TOOLS)/kubectl --context kind-rag-copilot

$(TOOLS)/kind:
	@mkdir -p $(TOOLS)
	curl -fsSLo $@ https://github.com/kubernetes-sigs/kind/releases/download/$(KIND_VERSION)/kind-linux-amd64
	echo "$$(curl -fsSL https://github.com/kubernetes-sigs/kind/releases/download/$(KIND_VERSION)/kind-linux-amd64.sha256sum | cut -d' ' -f1)  $@" | sha256sum -c -
	chmod +x $@

$(TOOLS)/kubectl:
	@mkdir -p $(TOOLS)
	curl -fsSLo $@ https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/linux/amd64/kubectl
	echo "$$(curl -fsSL https://dl.k8s.io/release/$(KUBECTL_VERSION)/bin/linux/amd64/kubectl.sha256)  $@" | sha256sum -c -
	chmod +x $@

k8s-tools: $(TOOLS)/kind $(TOOLS)/kubectl

# Local Kubernetes cluster (kind) running the production images and the deploy/k8s manifests. Rebuilds and
# redeploys on every run. The dev compose stack can stay up: its LGTM container is shared for monitoring queries.
k8s-up: k8s-tools
	@$(KIND) get clusters 2>/dev/null | grep -qx rag-copilot || $(KIND) create cluster --config deploy/k8s/kind/cluster.yaml
	docker build -q -t rag-copilot-api:kind api
	docker build -q --target prod -t rag-copilot-web:kind web
	docker build -q -t rag-copilot-payments:kind demo_payments
	$(KIND) load docker-image --name rag-copilot rag-copilot-api:kind rag-copilot-web:kind rag-copilot-payments:kind
	@# Lets pods reach the dev stack's LGTM container by name; fails harmlessly if already attached or not running.
	-@docker network connect kind rag-copilot-lgtm-1 2>/dev/null
	$(KUBECTL) apply -k deploy/k8s/kind/payments
	-@$(KUBECTL) -n copilot delete job migrate --ignore-not-found 2>/dev/null
	$(KUBECTL) apply -k deploy/k8s/kind/copilot
	$(KUBECTL) -n copilot wait --for=condition=complete job/migrate --timeout=300s
	@# Same image tag as before, so restart to pick up what was just loaded.
	$(KUBECTL) -n copilot rollout restart deployment/api deployment/web
	$(KUBECTL) -n copilot rollout status deployment/api deployment/web --timeout=300s

# Release a version of the demo payments service in the cluster as a real rollout. Usage: make k8s-release v2
k8s-release:
	$(KUBECTL) -n payments patch deployment payments --type=json -p '[{"op": "replace", "path": "/spec/template/metadata/labels/app.kubernetes.io~1version", "value": "$(ARGS)"}, {"op": "replace", "path": "/spec/template/spec/containers/0/env/0/value", "value": "$(ARGS)"}]'
	$(KUBECTL) -n payments rollout status deployment/payments --timeout=120s

# Checks RBAC from outside, then the deployment adapter from inside the API pod (with its own service account).
k8s-verify:
	@echo "Service account copilot:copilot-api may:"
	@for check in "patch deployments -n payments" "list replicasets -n payments" "delete deployments -n payments" \
		"create deployments -n payments" "get secrets -n payments" "get pods -n payments" "patch deployments -n copilot"; do \
		printf "  %-34s %s\n" "$$check" "$$($(KUBECTL) auth can-i $$check --as=system:serviceaccount:copilot:copilot-api)"; done
	$(MAKE) --no-print-directory k8s-release v2
	$(KUBECTL) -n copilot exec deploy/api -- python -m tests.k8s_check
	@echo "Web UI and API through the web Service:"
	@$(KUBECTL) -n copilot run web-check --rm -i --restart=Never --quiet --image=curlimages/curl:8.17.0 -- \
		sh -c 'curl -fsS -o /dev/null -w "  GET /             %{http_code}\n" http://web/ && curl -fsS -w "\n" http://web/v1/health'

# Open the UI running in the cluster at http://localhost:8090 (Ctrl-C to stop).
k8s-ui:
	$(KUBECTL) -n copilot port-forward svc/web 8090:80

k8s-down:
	$(KIND) delete cluster --name rag-copilot

# Accept positional arguments as Make goals.
%:
	@:
