"""Per-project rate limiting (A6).

Fixed-window (or sliding) limiter backed by Redis. Wired into the proxy only
when RATE_LIMIT_ENABLED=true; the proxy returns HTTP 429 when this returns
False. With the flag off (default) this never runs.
"""
from __future__ import annotations

from redis.asyncio import Redis


async def check_rate_limit(
    redis: Redis, project_id: int | None, limit: int, window_seconds: int
) -> bool:
    # ============================================================
    # ASSIGNMENT: A6 rate limit
    # ------------------------------------------------------------
    # Implement: a fixed-window (or sliding) per-project limiter in Redis using INCR + EXPIRE;
    #            return True if under `limit` within `window_seconds`, else False.
    # Why:       enforces per-project quotas when RATE_LIMIT_ENABLED=true (proxy returns 429).
    # Done when: the (limit+1)-th request inside the window returns False and the counter
    #            resets after the window expires.
    # Reference: https://redis.io/docs/latest/develop/use/patterns/twitter-clone/
    #            https://redis.io/commands/incr/
    #            https://redis.io/commands/expire/
    # ============================================================
    raise NotImplementedError("ASSIGNMENT: A6 rate limit")
