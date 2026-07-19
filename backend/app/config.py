"""Application configuration via pydantic-settings.

All feature flags default to False so the base proxy runs before any
assignment (A1..A10) is implemented.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- Infrastructure ----
    database_url: str = "postgresql+asyncpg://tap:tap@postgres:5432/tap"
    redis_url: str = "redis://redis:6379/0"

    # ---- Upstream provider ----
    upstream_base_url: str = "https://api.openai.com"
    upstream_timeout_seconds: float = 60.0

    # ---- Feature flags (all default OFF) ----
    auth_enabled: bool = False
    cache_enabled: bool = False
    cache_ttl_seconds: int = 3600
    rate_limit_enabled: bool = False
    default_rate_limit: int = 60
    rate_limit_window_seconds: int = 60
    logging_enabled: bool = False

    # ---- Web / CORS ----
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Parse a comma-separated string into a list[str]."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


settings = Settings()


@lru_cache
def get_settings() -> Settings:
    """Return the shared Settings singleton."""
    return settings
