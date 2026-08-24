"""Readiness must report a dead dependency.

Fly routes traffic on this, so a probe that returns 200 while Postgres is
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


async def test_a_broken_database_fails_readiness(client, monkeypatch):
    monkeypatch.setattr("app.main.engine", BrokenEngine())

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "unavailable"


async def test_a_broken_redis_fails_readiness(client, monkeypatch):
    async def explode(*args, **kwargs):
        raise ConnectionError("redis is down")

    monkeypatch.setattr("app.main.redis_client.ping", explode)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["redis"] == "unavailable"
