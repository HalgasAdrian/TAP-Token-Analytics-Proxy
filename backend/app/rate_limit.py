"""Per-key rate limiting (A6).

Fixed-window limiter backed by Redis. Wired into the proxy only when
RATE_LIMIT_ENABLED=true; the proxy returns HTTP 429 when this returns False.
With the flag off (default) this never runs.
"""
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

    A fixed window, not a sliding one. The window id is folded into the Redis
    key (`…:<scope>:<window>`), so each window starts from a fresh counter and
    old counters expire on their own — there is no reset bookkeeping and no
    read-modify-write race, because INCR is atomic.

    The cost of a fixed window is boundary burstiness: a caller can spend its
    full budget at the end of one window and again at the start of the next, so
    up to 2x`limit` can land in a short span straddling the boundary. A sliding
    window (a sorted set of timestamps) removes that at the price of storing one
    member per request. For per-key quotas measured in requests per minute, the
    fixed window is the right trade.

    `scope` is the identity being limited — the API key id, so budgets are
    independent per issued key as `ApiKey.rate_limit` intends. When auth is
    disabled there is no key, and all anonymous traffic shares one bucket.
    """
    if limit <= 0:
        # A zero or negative budget denies everything; without this, `count <=
        # limit` would still admit nothing but we would pay for a Redis call.
        return False
    if window_seconds <= 0:
        # No window means no meaningful budget to enforce.
        return True

    window = int(time.time()) // window_seconds
    key = f"{RATE_LIMIT_PREFIX}{scope if scope is not None else 'anonymous'}:{window}"

    try:
        pipeline = redis.pipeline()
        pipeline.incr(key)
        # Refreshed on every hit rather than only on creation: an INCR whose
        # EXPIRE never landed would leak a key that never expires.
        pipeline.expire(key, window_seconds)
        count, _ = await pipeline.execute()
    except RedisError:
        # Fail open. A Redis outage should not take the proxy down with it, and
        # an unenforced quota is the lesser failure — but it *is* unenforced
        # spend, hence the warning. Flip this to `return False` if protecting
        # the upstream budget matters more than staying available.
        logger.warning(
            "rate limit check failed; allowing request", exc_info=True
        )
        return True

    return int(count) <= limit
