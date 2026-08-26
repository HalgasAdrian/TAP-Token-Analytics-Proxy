"""Redis response cache."""

from __future__ import annotations

import hashlib
import json
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Bumping the version invalidates every existing entry.
CACHE_PREFIX = "tap:cache:v1:"

# Dropped before hashing: none of these change the response content. Everything
# that does — model, messages, temperature, top_p, seed, tools, stream — stays in
# the key, so a request at a different temperature is a separate entry rather
# than a false hit.
_NON_SEMANTIC_FIELDS: frozenset[str] = frozenset(
    {"stream_options", "metadata", "store", "user"}
)


def cache_key(payload: dict) -> str:
    """Return a deterministic key for a request payload.

    Content-addressed, so entries are shared across projects — which is what
    makes the cache save money. Prefix the project id here if an installation
    needs tenant isolation.
    """
    canonical = {
        key: value for key, value in payload.items() if key not in _NON_SEMANTIC_FIELDS
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return f"{CACHE_PREFIX}{hashlib.sha256(encoded.encode()).hexdigest()}"


async def cache_get(redis: Redis, key: str) -> dict | None:
    """Degrades to a miss rather than raising: a Redis outage should cost the
    proxy its cache, not its availability."""
    try:
        raw = await redis.get(key)
    except RedisError:
        logger.warning("cache lookup failed; treating as a miss", exc_info=True)
        return None

    if raw is None:
        return None

    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("discarding malformed cache entry")
        return None

    return value if isinstance(value, dict) else None


async def cache_set(redis: Redis, key: str, value: dict, ttl: int) -> None:
    if ttl <= 0:
        return

    try:
        await redis.set(key, json.dumps(value, default=str), ex=ttl)
    except RedisError:
        logger.warning("cache write failed; response not cached", exc_info=True)
