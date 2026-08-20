from redis.exceptions import RedisError

from app import rate_limit
from app.rate_limit import check_rate_limit


class BrokenRedis:
    def pipeline(self):
        raise RedisError("redis is down")


async def test_budget_is_spent_then_refused(redis):
    for attempt in range(3):
        assert await check_rate_limit(redis, 1, 3, 60) is True, attempt

    assert await check_rate_limit(redis, 1, 3, 60) is False
    assert await check_rate_limit(redis, 1, 3, 60) is False


async def test_each_scope_has_its_own_budget(redis):
    for _ in range(3):
        await check_rate_limit(redis, 1, 3, 60)
    assert await check_rate_limit(redis, 1, 3, 60) is False

    assert await check_rate_limit(redis, 2, 3, 60) is True


async def test_anonymous_traffic_shares_one_bucket(redis):
    assert await check_rate_limit(redis, None, 1, 60) is True
    assert await check_rate_limit(redis, None, 1, 60) is False


async def test_counter_resets_in_the_next_window(redis, monkeypatch):
    now = 1_000_000.0
    monkeypatch.setattr(rate_limit.time, "time", lambda: now)

    assert await check_rate_limit(redis, 1, 1, 60) is True
    assert await check_rate_limit(redis, 1, 1, 60) is False

    now += 60
    assert await check_rate_limit(redis, 1, 1, 60) is True


async def test_a_zero_budget_refuses_everything(redis):
    assert await check_rate_limit(redis, 1, 0, 60) is False
    assert await check_rate_limit(redis, 1, -5, 60) is False


async def test_a_zero_window_is_unenforced(redis):
    assert await check_rate_limit(redis, 1, 1, 0) is True
    assert await check_rate_limit(redis, 1, 1, 0) is True


async def test_the_key_carries_a_ttl_so_counters_expire(redis):
    await check_rate_limit(redis, 42, 5, 60)

    keys = [key async for key in redis.scan_iter(f"{rate_limit.RATE_LIMIT_PREFIX}*")]
    assert len(keys) == 1
    assert 0 < await redis.ttl(keys[0]) <= 60


async def test_a_redis_outage_fails_open():
    # Availability over enforcement: an unreachable Redis must not 429 everyone.
    assert await check_rate_limit(BrokenRedis(), 1, 1, 60) is True
