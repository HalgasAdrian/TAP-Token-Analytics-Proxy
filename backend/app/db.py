"""Async SQLAlchemy engine and session factory.

The schema is owned by Alembic. Nothing here creates tables, so concurrent
instances cannot race to build them.
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

# The deployment scales to zero and managed Postgres closes idle connections.
# Without pre-ping the first request after a quiet spell dies on a stale pooled
# connection; recycling retires them before they get that far.
engine = create_async_engine(
    settings.database_url, pool_pre_ping=True, pool_recycle=1800
)
AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
