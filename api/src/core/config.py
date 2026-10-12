import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Deployment-dependent configuration, read from environment variables."""

    log_level: str = "INFO"

    database_url: str
    redis_url: str

    # Any provider supported by LangChain's init_chat_model / init_embeddings.
    llm_provider: str
    llm_model: str
    llm_classifier_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None

    embedding_provider: str
    embedding_model: str
    # Must match the pgvector column size; changing it requires a migration and re-index.
    embedding_dimensions: int
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None

    prometheus_url: str
    loki_url: str
    tempo_url: str

    # Where deployment state comes from (and, later, where rollbacks are executed).
    deployment_backend: Literal["demo"]
    demo_payments_admin_url: str | None = None

    # HS256 signing key for access tokens; rotating it logs everyone out.
    auth_jwt_secret: Annotated[SecretStr, Field(min_length=32)]

    @model_validator(mode="after")
    def _require_backend_settings(self) -> Self:
        if self.deployment_backend == "demo" and not self.demo_payments_admin_url:
            raise ValueError("DEMO_PAYMENTS_ADMIN_URL is required when DEPLOYMENT_BACKEND=demo")
        return self


class MetricName(StrEnum):
    """Metrics the copilot can query; each needs a PromQL template in config/app.yaml."""

    LATENCY_P99_SECONDS = "latency_p99_seconds"
    ERROR_RATIO = "error_ratio"
    REQUEST_RATE = "request_rate"


class ServiceConfig(BaseModel):
    name: str
    title: str


class AuthConfig(BaseModel):
    access_token_ttl_minutes: int


class MonitoringConfig(BaseModel):
    metrics: dict[MetricName, str]
    error_logs: str
    slow_traces: str

    @model_validator(mode="after")
    def _require_every_metric(self) -> Self:
        if missing := set(MetricName) - set(self.metrics):
            raise ValueError(f"monitoring.metrics is missing templates for {sorted(missing)}")
        return self


class AppConfig(BaseModel):
    """Deployment-independent configuration from config/app.yaml."""

    service: ServiceConfig
    auth: AuthConfig
    monitoring: MonitoringConfig
    version: str


def _load_app_config() -> AppConfig:
    data = yaml.safe_load((API_ROOT / "config" / "app.yaml").read_text())
    # pyproject.toml stays the single source of truth for the version.
    pyproject = tomllib.loads((API_ROOT / "pyproject.toml").read_text())
    return AppConfig(**data, version=pyproject["project"]["version"])


settings = Settings()
app_config = _load_app_config()
