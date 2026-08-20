from redis.exceptions import RedisError

from app.cache import cache_get, cache_key, cache_set


class BrokenRedis:
    async def get(self, key):
        raise RedisError("redis is down")

    async def set(self, key, value, ex=None):
        raise RedisError("redis is down")


KEY = cache_key({"model": "gpt-4o", "messages": []})
VALUE = {"id": "chatcmpl-1", "usage": {"prompt_tokens": 5, "completion_tokens": 2}}


async def test_roundtrip(redis):
    await cache_set(redis, KEY, VALUE, 60)
    assert await cache_get(redis, KEY) == VALUE


async def test_missing_key_is_a_miss(redis):
    assert await cache_get(redis, KEY) is None


async def test_ttl_is_applied(redis):
    await cache_set(redis, KEY, VALUE, 60)
    assert 0 < await redis.ttl(KEY) <= 60


async def test_non_positive_ttl_stores_nothing(redis):
    await cache_set(redis, KEY, VALUE, 0)
    assert await cache_get(redis, KEY) is None

    await cache_set(redis, KEY, VALUE, -1)
    assert await cache_get(redis, KEY) is None


async def test_malformed_entry_reads_as_a_miss(redis):
    await redis.set(KEY, "{not json")
    assert await cache_get(redis, KEY) is None


async def test_non_object_entry_reads_as_a_miss(redis):
    await redis.set(KEY, "[1, 2, 3]")
    assert await cache_get(redis, KEY) is None


async def test_distinct_payloads_do_not_collide(redis):
    other = cache_key({"model": "gpt-4o-mini", "messages": []})
    await cache_set(redis, KEY, VALUE, 60)

    assert await cache_get(redis, other) is None


async def test_unserialisable_value_does_not_raise(redis):
    await cache_set(redis, KEY, {"when": object()}, 60)
    assert await cache_get(redis, KEY) is not None


async def test_a_redis_outage_degrades_to_a_miss():
    # A cache outage should cost the proxy its cache, not its availability.
    assert await cache_get(BrokenRedis(), KEY) is None


async def test_a_redis_outage_on_write_is_swallowed():
    await cache_set(BrokenRedis(), KEY, VALUE, 60)
