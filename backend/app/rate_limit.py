"""Fixed-window per-key rate limiting, backed by Redis."""

from __future__ import annotations

import logging
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

RATE_LIMIT_PREFIX = "tap:ratelimit:v1:"


async def check_rate_limit(
    redis: Redis, scope: int | str | None, limit: int, window_seconds: int
) -> bool:
    """Consume one unit of `scope`'s budget; return False once it is exhausted.

    The window id is part of the key, so each window starts from a fresh counter
    and old counters expire on their own. A fixed window admits up to 2x`limit`
    across a boundary; a sliding window would remove that at the cost of storing
    one member per request, which per-minute quotas do not justify.

    `scope` is the API key id, or None for unauthenticated traffic, which shares
    a single bucket.
    """
    if limit <= 0:
        return False
    if window_seconds <= 0:
        return True

    window = int(time.time()) // window_seconds
    key = f"{RATE_LIMIT_PREFIX}{scope if scope is not None else 'anonymous'}:{window}"

    try:
        pipeline = redis.pipeline()
        pipeline.incr(key)
        pipeline.expire(key, window_seconds)
        count, _ = await pipeline.execute()
    except RedisError:
        # Fails open: a Redis outage should not take the proxy down with it.
        # Return False instead to protect the upstream budget.
        logger.warning("rate limit check failed; allowing request", exc_info=True)
        return True

    return int(count) <= limit
