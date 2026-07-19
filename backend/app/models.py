"""SQLAlchemy 2.0 ORM models for TAP (Token Analytics Proxy).

Fully implemented wiring — contains NO assignment stubs.

Security invariant: the Authorization header, API keys, and key material are
NEVER stored here. Only a SHA-256 `key_hash` is persisted (see ApiKey).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.db import Base


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    request_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    key_hash: Mapped[str] = mapped_column(
        String, index=True, unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    rate_limit: Mapped[int] = mapped_column(
        Integer, default=settings.default_rate_limit, nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
