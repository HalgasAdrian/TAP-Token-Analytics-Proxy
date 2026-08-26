"""Shared async Redis client and FastAPI dependency."""

from __future__ import annotations

import redis.asyncio as redis

from app.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> redis.Redis:
    return redis_client


async def close_redis() -> None:
    await redis_client.aclose()
