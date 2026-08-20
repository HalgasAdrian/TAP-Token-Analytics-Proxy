"""Readiness must reflect the dependencies the current configuration needs.

Fly routes traffic on this, so a probe that returns 200 while the database is
unreachable would keep a broken instance in rotation.
"""

from app.config import settings


class BrokenEngine:
    """AsyncEngine.connect is read-only, so the engine itself is replaced."""

    def connect(self):
        raise ConnectionError("database is down")


async def test_liveness_is_unconditional(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_reports_both_dependencies(client):
    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["redis"] == "ok"


async def test_readiness_is_public(client):
    settings.dashboard_password = "secret"

    assert (await client.get("/health/ready")).status_code == 200


async def test_a_broken_database_fails_readiness_when_it_is_needed(client, monkeypatch):
    settings.logging_enabled = True
    monkeypatch.setattr("app.main.engine", BrokenEngine())

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "unavailable"


async def test_a_broken_database_is_tolerated_when_nothing_needs_it(
    client, monkeypatch
):
    settings.logging_enabled = False
    settings.auth_enabled = False
    monkeypatch.setattr("app.main.engine", BrokenEngine())

    response = await client.get("/health/ready")

    # Pure pass-through proxying does not touch the database, so the instance
    # can still serve traffic.
    assert response.status_code == 200
    assert response.json()["database"] == "unavailable"


async def test_a_broken_redis_fails_readiness_when_the_cache_is_on(client, monkeypatch):
    settings.cache_enabled = True

    async def explode(*args, **kwargs):
        raise ConnectionError("redis is down")

    monkeypatch.setattr("app.main.redis_client.ping", explode)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["redis"] == "unavailable"


async def test_a_broken_redis_is_tolerated_when_no_feature_needs_it(
    client, monkeypatch
):
    settings.cache_enabled = False
    settings.rate_limit_enabled = False

    async def explode(*args, **kwargs):
        raise ConnectionError("redis is down")

    monkeypatch.setattr("app.main.redis_client.ping", explode)

    response = await client.get("/health/ready")

    assert response.status_code == 200
