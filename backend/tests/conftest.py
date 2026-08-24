"""Shared test fixtures.

Tests run against a real Postgres and Redis — the metrics queries depend on
date_trunc, percentile_cont, and JSONB, none of which a substitute provides.
Both are pointed at a dedicated database and Redis index so a test run cannot
touch development data.
"""

import os

# Assigned, not setdefault: the container inherits DATABASE_URL from the .env
# used to run the app, and setdefault would leave it pointing at the development
# database — which the truncating fixture below would then wipe. Override with
# TEST_DATABASE_URL / TEST_REDIS_URL (CI does).
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://tap:tap@postgres:5432/tap_test"
)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://redis:6379/1")
# Strip the mock upstream's synthetic latency so the suite is not paced by it.
os.environ["MOCK_BASE_MS"] = "0"
os.environ["MOCK_JITTER_MS"] = "0"

import subprocess
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.auth import generate_api_key, hash_api_key
from app.config import settings
from app.db import engine
from app.main import app
from app.models import ApiKey, Project
from app.redis_client import redis_client


def _guard_against_wiping_real_data() -> None:
    """Refuse to run if the targets are not obviously disposable.

    The fixtures truncate every table and flush the Redis database. A
    misconfigured URL would therefore destroy real data, so the names are
    checked before anything connects.
    """
    database = make_url(settings.database_url).database or ""
    if not database.endswith("_test"):
        raise RuntimeError(
            f"refusing to run: database {database!r} is not a *_test database. "
            "Set TEST_DATABASE_URL."
        )

    redis_index = urlparse(settings.redis_url).path.lstrip("/") or "0"
    if redis_index == "0":
        raise RuntimeError(
            "refusing to run: Redis index 0 is the application cache. "
            "Set TEST_REDIS_URL to a different index."
        )


async def _create_test_database() -> None:
    url = make_url(settings.database_url)
    admin_dsn = (
        f"postgresql://{url.username}:{url.password}@{url.host}:{url.port}/postgres"
    )
    connection = await asyncpg.connect(admin_dsn)
    try:
        exists = await connection.fetchval(
            "select 1 from pg_database where datname = $1", url.database
        )
        if not exists:
            await connection.execute(f'create database "{url.database}"')
    finally:
        await connection.close()


def _run_migrations() -> None:
    """Build the test schema with Alembic, not create_all.

    Run as a subprocess for two reasons: migrations/env.py calls asyncio.run,
    which cannot nest inside the running test loop; and it exercises the exact
    command the deploy runs, so a broken migration fails here first.
    """
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
        )


@pytest.fixture(scope="session", autouse=True)
async def _database():
    _guard_against_wiping_real_data()
    await _create_test_database()
    _run_migrations()
    yield
    await engine.dispose()
    await redis_client.aclose()


# Every test starts from these settings, regardless of the .env the container
# was started with.
_BASELINE_SETTINGS = {
    "auth_enabled": False,
    "cache_ttl_seconds": 3600,
    "default_rate_limit": 60,
    "rate_limit_window_seconds": 60,
    "max_body_bytes": 16384,
    "log_retention_days": 30,
    "metrics_token": "",
    "dashboard_password": "",
}


@pytest.fixture(autouse=True)
async def _clean_state():
    """Reset all mutable state so tests cannot leak into one another."""
    async with engine.begin() as connection:
        await connection.execute(
            text("truncate request_logs, api_keys, projects restart identity cascade")
        )
    await redis_client.flushdb()

    for name, value in _BASELINE_SETTINGS.items():
        setattr(settings, name, value)
    yield


@pytest.fixture
def redis():
    return redis_client


@pytest.fixture
def issue_key(session):
    """Create a project and an API key, returning the plaintext and project."""

    async def _issue(*, project_active=True, key_active=True, rate_limit=60):
        project = Project(name="Test", active=project_active)
        session.add(project)
        await session.flush()

        plaintext = generate_api_key()
        session.add(
            ApiKey(
                project_id=project.id,
                name="test",
                key_hash=hash_api_key(plaintext),
                rate_limit=rate_limit,
                active=key_active,
            )
        )
        await session.commit()
        return plaintext, project

    return _issue


@pytest.fixture
async def session():
    from app.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db_session:
        yield db_session


@pytest.fixture
async def client():
    """The proxy, with the mock provider wired in as its upstream.

    The mock is mounted as an ASGI app rather than reached over the network, so
    the whole request path is exercised without a socket or a real provider.
    Lifespan is not run, so app.state.http_client is set here instead.
    """
    from dev.mock_upstream import app as mock_app

    upstream = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app))
    app.state.http_client = upstream
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://tap"
        ) as tap_client:
            yield tap_client
    finally:
        await upstream.aclose()
