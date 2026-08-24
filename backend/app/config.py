"""Application settings, read from environment variables or the .env file."""

from __future__ import annotations

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- Infrastructure ----
    database_url: str = "postgresql+asyncpg://tap:tap@postgres:5432/tap"
    redis_url: str = "redis://redis:6379/0"

    # ---- Upstream provider ----
    upstream_base_url: str = "https://api.openai.com"
    upstream_timeout_seconds: float = 60.0

    # ---- Authentication ----
    # Require a TAP-issued API key on /v1 requests. Off by default so local
    # development works without issuing a key first.
    auth_enabled: bool = False

    # ---- Cache ----
    cache_ttl_seconds: int = 3600

    # ---- Rate limiting ----
    # Requests allowed per window. Each API key can override the default.
    default_rate_limit: int = 60
    rate_limit_window_seconds: int = 60

    # ---- Table growth ----
    # Request and response bodies take up most of the space in request_logs. A
    # body whose JSON is larger than this is replaced with a size marker.
    max_body_bytes: int = 16384
    # Age at which `prune-logs` deletes rows; 0 means keep everything.
    log_retention_days: int = 30

    # ---- Dashboard and metrics access ----
    # Bearer token for programmatic access to /metrics.
    metrics_token: str = ""
    # HTTP Basic password guarding the dashboard and /metrics in a browser.
    dashboard_password: str = ""

    # ---- Web / CORS ----
    # NoDecode skips the JSON pre-parse, so the comma-separated environment
    # value reaches _split_cors_origins.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Parse a comma-separated string into a list[str]."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


settings = Settings()
