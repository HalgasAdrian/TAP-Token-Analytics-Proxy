"""Async SQLAlchemy engine and session factory.

The schema is owned by Alembic — run `alembic upgrade head`. Nothing here
creates tables, so concurrent instances cannot race to build them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Pre-ping because the deployment scales to zero and managed Postgres closes
# idle connections: without it the first request after a quiet spell dies on a
# dead pooled connection, and only the request after that succeeds. Recycling
# retires connections before they reach that state.
engine = create_async_engine(
    settings.database_url, pool_pre_ping=True, pool_recycle=1800
)
AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession."""
    async with AsyncSessionLocal() as session:
        yield session
