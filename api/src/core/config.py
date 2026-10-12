import tomllib
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field, SecretStr
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

    # HS256 signing key for access tokens; rotating it logs everyone out.
    auth_jwt_secret: Annotated[SecretStr, Field(min_length=32)]


class ServiceConfig(BaseModel):
    name: str
    title: str


class AuthConfig(BaseModel):
    access_token_ttl_minutes: int


class AppConfig(BaseModel):
    """Deployment-independent configuration from config/app.yaml."""

    service: ServiceConfig
    auth: AuthConfig
    version: str


def _load_app_config() -> AppConfig:
    data = yaml.safe_load((API_ROOT / "config" / "app.yaml").read_text())
    # pyproject.toml stays the single source of truth for the version.
    pyproject = tomllib.loads((API_ROOT / "pyproject.toml").read_text())
    return AppConfig(**data, version=pyproject["project"]["version"])


settings = Settings()
app_config = _load_app_config()
