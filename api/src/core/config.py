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

    # Where deployment state comes from and where rollbacks, restarts and scaling are carried out.
    deployment_backend: Literal["demo", "kubernetes"]
    demo_payments_admin_url: str | None = None
    # true: use the pod's service account; false: use the local kubeconfig (KUBECONFIG or ~/.kube/config).
    kubernetes_in_cluster: bool = True
    # The namespace whose Deployments the copilot inspects and changes; service names are Deployment names.
    kubernetes_namespace: str | None = None

    # The API's own traces, metrics and logs, exported over OTLP/HTTP (e.g. to the LGTM stack's collector).
    telemetry_traces_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None

    # HS256 signing key for access tokens; rotating it logs everyone out.
    auth_jwt_secret: Annotated[SecretStr, Field(min_length=32)]

    @model_validator(mode="after")
    def _require_backend_settings(self) -> Self:
        if self.deployment_backend == "demo" and not self.demo_payments_admin_url:
            raise ValueError("DEMO_PAYMENTS_ADMIN_URL is required when DEPLOYMENT_BACKEND=demo")
        if self.deployment_backend == "kubernetes" and not self.kubernetes_namespace:
            raise ValueError("KUBERNETES_NAMESPACE is required when DEPLOYMENT_BACKEND=kubernetes")
        if self.telemetry_traces_enabled and not self.otel_exporter_otlp_endpoint:
            raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT is required when TELEMETRY_TRACES_ENABLED=true")
        return self


class MetricName(StrEnum):
    """Metrics the copilot can query; each needs a PromQL template in config/app.yaml."""

    LATENCY_P99_SECONDS = "latency_p99_seconds"
    ERROR_RATIO = "error_ratio"
    REQUEST_RATE = "request_rate"


class ActionName(StrEnum):
    """Remediation actions the copilot can propose; each needs an entry in remediation.actions."""

    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    RESTART_DEPLOYMENT = "restart_deployment"
    SCALE_DEPLOYMENT = "scale_deployment"


class RiskLevel(StrEnum):
    LOW = "low"
    HIGH = "high"


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


class KnowledgeConfig(BaseModel):
    top_k: int
    chunk_max_chars: int
    chunk_overlap_chars: int


class CopilotConfig(BaseModel):
    llm_timeout_seconds: float


class ActionConfig(BaseModel):
    risk: RiskLevel
    description: str


class VerificationConfig(BaseModel):
    thresholds: dict[MetricName, float]
    timeout_seconds: float
    poll_seconds: float


class RemediationConfig(BaseModel):
    actions: dict[ActionName, ActionConfig]
    max_replicas: int
    verification: VerificationConfig

    @model_validator(mode="after")
    def _require_every_action(self) -> Self:
        if missing := set(ActionName) - set(self.actions):
            raise ValueError(f"remediation.actions is missing {sorted(missing)}")
        return self


class AppConfig(BaseModel):
    """Deployment-independent configuration from config/app.yaml."""

    service: ServiceConfig
    auth: AuthConfig
    monitoring: MonitoringConfig
    knowledge: KnowledgeConfig
    copilot: CopilotConfig
    remediation: RemediationConfig
    version: str


def _load_app_config() -> AppConfig:
    data = yaml.safe_load((API_ROOT / "config" / "app.yaml").read_text())
    # pyproject.toml stays the single source of truth for the version.
    pyproject = tomllib.loads((API_ROOT / "pyproject.toml").read_text())
    return AppConfig(**data, version=pyproject["project"]["version"])


settings = Settings()  # pyright: ignore[reportCallIssue]  (fields are read from the environment)
app_config = _load_app_config()
