"""Async SQLAlchemy engine, session factory, and DB bootstrap helpers.

Alembic is the production migration path; `create_all` here is dev convenience.
"""

from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url)
AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession (async generator)."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create all tables (dev convenience; Alembic is the prod path)."""
    import app.models  # noqa: F401  (ensure models are registered on Base.metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
