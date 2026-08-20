"""Response cache (A5).

Builds a stable cache key from a request payload and provides get/set helpers
for JSON values in Redis with a TTL. Wired into the proxy only when
CACHE_ENABLED=true; with the flag off (default) none of these run.

SECURITY: never place the Authorization header or API key material into a cache
key or cached value. `cache_key` sees only the parsed request body, never
headers, so the key is a pure function of the payload.
"""
from __future__ import annotations

import hashlib
import json
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Versioned prefix: bumping it invalidates every existing entry at once, which
# is the escape hatch if the key or value format ever changes.
CACHE_PREFIX = "tap:cache:v1:"

# Fields dropped before hashing because they cannot change the response
# *content*. Everything that does affect the output — model, messages,
# temperature, top_p, seed, max_tokens, tools, stream — stays in the key, so a
# request at a different temperature is a different entry rather than a false
# hit.
#
# `stream` is deliberately retained: an SSE response and a buffered JSON
# response are not interchangeable, and keying on it prevents one from ever
# being served in place of the other.
_NON_SEMANTIC_FIELDS: frozenset[str] = frozenset(
    {"stream_options", "metadata", "store", "user"}
)


def cache_key(payload: dict) -> str:
    """Return a deterministic Redis key for a request payload.

    The key is content-addressed: `sort_keys` makes it independent of JSON
    member order, so two semantically identical requests collide by design.

    Note the caching policy this implies. Entries are keyed on request content
    alone and are therefore shared across projects — the point of the cache is
    to avoid paying twice for the same prompt, and a per-tenant cache would
    forfeit most of that. Namespace it by prefixing the project id here if an
    installation needs strict tenant isolation instead.

    A request with temperature > 0 will be served the first sampled response
    for the remainder of the TTL. That is the deliberate trade — cost and
    latency in exchange for variety — and it is why CACHE_ENABLED is opt-in.
    """
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in _NON_SEMANTIC_FIELDS
    }
    # default=str keeps a surprising value (e.g. a non-JSON scalar) from raising
    # inside what is only ever a hash input.
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), default=str
    )
    return f"{CACHE_PREFIX}{hashlib.sha256(encoded.encode()).hexdigest()}"


async def cache_get(redis: Redis, key: str) -> dict | None:
    """Return the cached JSON object for `key`, or None on a miss.

    Degrades to a miss rather than raising: a Redis outage should cost the
    proxy its cache, not its availability.
    """
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
        # An unparseable entry is indistinguishable from a miss to the caller.
        logger.warning("discarding malformed cache entry")
        return None

    # Only object bodies are cached, so anything else is not a usable hit.
    return value if isinstance(value, dict) else None


async def cache_set(redis: Redis, key: str, value: dict, ttl: int) -> None:
    """Store `value` as JSON under `key` with a `ttl`-second expiry.

    A non-positive TTL is treated as "caching disabled" — storing without an
    expiry would leak entries forever.
    """
    if ttl <= 0:
        return

    try:
        await redis.set(key, json.dumps(value, default=str), ex=ttl)
    except RedisError:
        logger.warning("cache write failed; response not cached", exc_info=True)
