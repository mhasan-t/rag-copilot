# Enterprise AI Operations Copilot

## Functionality:

1. User asks an operational question.
2. System classifies the task.
3. RAG searches internal documents/runbooks.
4. Agent can query monitoring systems.
5. Agent can inspect recent incidents.
6. Agent can propose remediation.
7. High-risk actions require approval.
8. Approved actions execute through typed tools.
9. Every execution is traced.
10. Evaluation dataset tests behavior.

## Example:

### Prompts

“Why is the payments service showing a latency spike?”

### Process

classify request
↓
retrieve monitoring runbook
↓
query metrics
↓
query recent logs
↓
query deployment state
↓
summarize evidence
↓
propose likely cause
↓
propose remediation
↓
human approval
↓
execute rollback
↓
verify latency

## Stack

Python
FastAPI
PostgreSQL
pgvector
Redis
Docker
Kubernetes
OpenTelemetry
Grafana
LangChain
LangGraph

# Repository Instructions

Before making any changes in this repository:

1. Read the instructions below.
2. Follow the rules specified by the instructions below.
3. Apply all enabled rules when writing, modifying, refactoring, or reviewing code.
4. Project-specific overrides take precedence over general rules.
5. Do not claim that tests, builds, or checks passed unless you actually ran them.

## Purpose

Act as a disciplined software engineer when creating, modifying, reviewing, or refactoring code.

Apply the universal rules in this file to every project.

Do not invent or apply rules from technologies that are not used by the project.

## Rule precedence

- **Priority 1:** Explicit requirements in the current task.
- **Priority 2:** Framework-specific rules.
- **Priority 3:** Architecture-specific rules.
- **Priority 4:** Technology-specific rules.
- **Priority 5:** Universal rules in this file.
- **Conflict resolution:** If two applicable rules conflict, follow the higher-priority rule. If the conflict cannot be resolved from this hierarchy, preserve the existing project convention and explain the conflict before making a broad architectural change.

## Universal rules

### Architecture and design

- Use modular architecture appropriate to the project.
- Organize business logic by domain
- Keep responsibilities cohesive and boundaries explicit.
- Keep unrelated functionality separated.
- Prefer small, focused modules, classes, and functions.
- Keep code reusable without introducing unnecessary abstractions.
- Maintain a single source of truth for each piece of information.
- Use global exception handlers.
- Global exception handlers should catch exceptions to log and return API response.
- Raise exceptions instead of printing errors logs and returning API response manually.
- Do not change the version tag of anything (prompts, api, logs, data etc) unless explicitly said.

### Files and folders

- A file should contain only closely related functions, classes, or definitions.
- A file should normally contain one primary class; tightly coupled helper classes may remain with it.
- Group related classes, models, routers, controllers, services, and schemas in meaningful folders.
- Keep schemas near the layer or module that owns their responsibility.
- Prefer files under 300 lines.
- **Exception:** Exceed 300 lines when splitting would reduce cohesion or readability.
- The name of the service files must contain the word `service` and the repository file names must contain the word `repository`
- Do not split files merely to satisfy the line-count guideline.
- Don't organize files according to what kind of code they contain. Organize them according to what needs to change together.
- Don't overfactor the files. If a file only contains 5 lines of code, it might be overfactored.

### Functions and methods

- Prefer functions and methods under 30 lines.
- **Exception:** Exceed 30 lines when extracting helpers would make the implementation less clear.
- Extract helpers when they improve readability or isolate reusable logic.
- Keep non-exported helpers private or local when the language supports it.
- Keep helper methods at the bottom of a class when that matches project conventions.
- Use standalone utility functions when a class would add unnecessary complexity.
- Use the Factory pattern when object creation or dependency selection genuinely benefits from it.
- Repositories only handle ORM calls or execute SQLs and return the data. - Repositories shouldn’t know about any DTO, it should return the data as it comes from the ORM. It shouldn't commit.
- Services should contain the core business logic and is responsible for persistence. So services will commit DB changes, but will use Query to get DB data and Repository to mutate DB data.
- Services should return data in DTO formats.

### Readability

- Use precise and meaningful names.
- Prefer clear code over clever code.
- Use appropriate spacing, formatting, types, and structure.
- Do not introduce abstractions that hide simple behavior without a clear benefit.

### Comments

- Comments must provide information needed to understand implementation logic.
- Comment functions, classes, components, or significant blocks when their purpose or logic is not obvious.
- Explain why non-obvious code exists rather than restating what the code literally does.
- If parameters, return values, side effects, or assumptions are not clear from a definition, document them using the language's conventional format.
- For complex logic, add comments around logical blocks where they materially help a new engineer understand the implementation.
- Do not explain programming-language syntax or obvious library usage.
- CSS and UI components should also be documented when their implementation requires explanation.

#### Database columns

- Document database columns unless their purpose is obvious, such as common IDs and timestamps.

### Database

#### Uuid

- Prefer UUID generation by the database.
- **Exception:** The application may generate an ID when multiple objects need the same ID before persistence.

#### Naming

- **Table names:** snake_case
- **Column names:** snake_case
- **Code representation:** camelCase
- **Example:** ORM class: AnalyticsInstallation. Application attribute: createdAt. Database table: analytics_installation. Database column: created_at.

#### Migrations

- A migration should normally change only one table.
- **Exception:** A migration may change multiple tightly coupled tables when a feature requires it.

### Environment variables

- Group related environment variables together.
- Add comments describing non-obvious variable groups.
- Keep common variables at the appropriate top-level scope and application-specific variables within their application.
- Do not store versions, package names, service names, titles, or static software metadata in environment variables.
- Store deployment-independent configuration in configuration files.
- Secret values should appear at the bottom of example environment files.
- Dependent variables must be conditionally validated based on their controlling variable.
- **Example:** If ML*EXPORT_ENABLED=false, ML_EXPORT_SCHEDULE_CRON, ML_EXPORT_BATCH_SIZE, and other ML_EXPORT*\* values should not be required.
- DO NOT RENAME ENVIRONMENT VARIABLES. The same name should be consistent in `.env` file, `dockerfile`, `docker-compose` files, `kubernetes` config files, and inside the application.

#### Example files

- Create .env.local.example and .env.production.example when environment files are used.
- .env.local.example should be usable as the basis for local development.
- .env.production.example should contain dummy values or descriptions, never real secrets.
- In monorepos, include the application name in environment example filenames.
- Deployment systems must preserve separation between environment files instead of merging unrelated production variables.

### Logging

- Use a global logger instance.
- Globally catch and log all raised errors.
- Raise exceptions to be catched by the global logger middleware instead of writing `try...catch...` or `logger.error...` manually.
- Log every meaningful operation.
- Logs must contain enough context to diagnose failures and trace important operations.
- Never log passwords, API keys, tokens, private keys, or other sensitive values.

### Formatting

- Run the project's configured formatter after modifying code.
- Do not introduce a new formatter solely to satisfy this guideline.

### Configuration

- Keep configuration in the project's designated config location.
- Keep deployment-independent configuration out of environment variables.
- Store versions, package names, service names, titles, and software metadata in configuration files.

### Docker

- Don't put the `venv` or `node_modules` in the app folder. Keep them in `/opt` so that the dev containers can mount and change ownership of them.

### Design

- Use Tailwind when Tailwind is part of the project's frontend stack.
- Use global design tokens or variables for repeated colors, typography, spacing, and other design values.

### Documentation

- Update documentation in /docs when changes affect architecture, behavior, APIs, configuration, deployment, or developer workflows.
- Do not create documentation links that depend on fragile source-file paths when the paths can change.
- Prefer stable conceptual documentation over implementation-path documentation.

### Testing

- Test observable behavior rather than implementation details.
- Write tests for meaningful API endpoints and domain or business logic.
- Do not create isolated tests for trivial helpers when their behavior is adequately covered by larger tests.

#### Api tests

- Verify response behavior, relevant database changes, and important business behavior.

#### Assertions

- Assertions should clearly express the behavior being verified.
- Document complex assertions when their purpose or tested behavior is not obvious.

### Developer experience

- Always make changes in the working tree. Never modify staged files.
- Use `Makefile` for spinning up dev servers, stopping, cleaning, and inspecting containers, data, and servers.

#### Example makefile

```
# Core development services never include Shopify or observability containers.
DEV_COMPOSE = docker compose --env-file .env -f docker-compose.dev.yaml
DEV_OBSERVABILITY_COMPOSE = $(DEV_COMPOSE) --profile observability

# Everything after the first Make goal is treated as positional arguments.
ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))

.PHONY: dev test lint autogen_migrations apply_alembic manual_test prepare-env up observability-up observability-down down logs observability-logs migrate revision psql app_bash python clear_shopify_sessions

dev:
	cd size_api && uv run uvicorn src.presentation.api.v1.main:app --reload --log-level debug

test:
	cd size_api && uv run pytest

lint:
	cd size_api && uv run ruff check .

autogen_migrations:
	cd size_api && uv run alembic revision --autogenerate -m "$(m)"

apply_alembic:
	cd size_api && uv run alembic upgrade head

manual_test:
	cd size_api && uv run python -m tests.manual_test

# Create local configuration once while preserving every developer override.
prepare-env:
	@test -f .env || cp .env.local.example .env
	@test -f size_api/.env || cp size_api/.env.local.example size_api/.env
	@test -f shopify_app/.env || cp shopify_app/.env.local.example shopify_app/.env
	@test -f dashboard/.env || cp dashboard/.env.local.example dashboard/.env
	@mkdir -p shopify_app/.shopify/dev-bundle

compose:
	$(DEV_COMPOSE) $(ARGS)

up-f: prepare-env
	TELEMETRY_TRACES_ENABLED=false $(DEV_COMPOSE) up --build --remove-orphans $(ARGS)

up: prepare-env
	TELEMETRY_TRACES_ENABLED=false $(DEV_COMPOSE) up -d --build --remove-orphans $(ARGS)

# Start core and observability services under the same Compose project.
observability-up: prepare-env
	TELEMETRY_TRACES_ENABLED=true $(DEV_OBSERVABILITY_COMPOSE) up --build --remove-orphans $(ARGS)

# Return the project to core-only mode and remove observability containers.
observability-down: prepare-env
	$(DEV_OBSERVABILITY_COMPOSE) down --remove-orphans
	TELEMETRY_TRACES_ENABLED=false $(DEV_COMPOSE) up --build --remove-orphans $(ARGS)

down:
	$(DEV_OBSERVABILITY_COMPOSE) down --remove-orphans $(ARGS)

logs:
	$(DEV_COMPOSE) logs --follow $(ARGS)

observability-logs:
	$(DEV_OBSERVABILITY_COMPOSE) logs --follow $(ARGS)

migrate:
	$(DEV_COMPOSE) run --rm size_api-migrate $(ARGS)

revision:
	$(DEV_COMPOSE) exec api uv run --no-sync alembic revision --autogenerate -m "$(m)"

psql:
	$(DEV_COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' $(ARGS)

app_bash:
	$(DEV_COMPOSE) exec api bash $(ARGS)

python:
	$(DEV_COMPOSE) exec api uv run --no-sync python $(ARGS)

clear_shopify_sessions:
	$(DEV_COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$SHOPIFY_DB_NAME" -c '\''DELETE FROM "Session" WHERE shop = '\''\''${shop}'\''\'';'\'''


# Accept positional arguments as Make goals.
%:
	@:
```

## Implementation workflow

- **Step 1:** Read the task requirements.
- **Step 2:** Inspect the existing implementation and project structure.
- **Step 4:** Implement the smallest clean change that satisfies the task.
- **Step 5:** Preserve existing conventions unless they conflict with a higher-priority rule.
- **Step 6:** Avoid unrelated refactoring.
- **Step 7:** Run applicable formatting, linting, type checking, and tests.
- **Step 8:** Update documentation when required.
- **Step 9:** Verify logging, security, database, and architectural constraints for changed code.

## Project configuration

### Project Data

#### Project

- **Name:** PROJECT_NAME
- **Language:** python
- **Architecture:** modular
- **Database:** postgresql
- **Package manager:** uv

#### Enabled rules

- **Technology:** python
- **Framework:** fastapi
- **Architecture:** modular

#### Project overrides

- All public APIs must use /v1.

## Technology python

### Naming

- Follow PEP 8 naming conventions.

### Package management

- Use uv for Python package management.

### Environment

- Use Pydantic for reading and validating environment variables when the project uses Pydantic.
- Keep related environment variables in their appropriate configuration module or file.

## Technology fastapi

### Architecture

- Follow Onion Architecture.

### Routers

- Routers should define routes and connect them to controllers.

  Routers should contain no business logic.

### Controllers

- Controllers should validate requests and call services.

  Controllers should contain no business logic.

### Dependencies

- Dependency methods should live in their own files.

### Authorization

- For authorization, use Policy classes similar to the policy pattern used by Ruby on Rails.

### Naming

- Use filenames such as \_router.py and \_controller.py where this convention is adopted by the project.

### Request state

#### Authentication

- When user authentication exists, request.state.user should contain the authenticated user information.

#### Multi tenancy

- When multi-tenancy exists, request.state.tenant should contain the current tenant information.

## Architecture modular

- Organize code around cohesive modules or business domains.
- Each module should expose a small and intentional public interface.
- Avoid unnecessary dependencies between unrelated modules.
- Keep implementation details private to the module whenever possible.
