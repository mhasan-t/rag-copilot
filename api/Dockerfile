FROM python:3.14-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# The venv lives in /opt so the dev bind mount of the source tree over /app doesn't hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

# Production installs runtime dependencies only; docker-compose.dev.yaml passes "" to include dev tools.
ARG UV_SYNC_FLAGS=--no-dev

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-install-project $UV_SYNC_FLAGS

COPY . .

RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
