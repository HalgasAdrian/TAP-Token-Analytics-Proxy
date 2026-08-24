"""FastAPI application entrypoint.

Wires the proxy and metrics routers and manages the shared httpx client, DB, and
Redis lifecycle.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app import metrics, proxy
from app.access import UNAUTHORIZED_HEADERS, access_is_configured, is_authorised
from app.config import settings
from app.db import engine
from app.redis_client import close_redis, redis_client

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Hold one shared httpx client and connection pool for the process."""
    app.state.http_client = httpx.AsyncClient(timeout=settings.upstream_timeout_seconds)
    await redis_client.ping()
    if not access_is_configured():
        logger.warning(
            "neither METRICS_TOKEN nor DASHBOARD_PASSWORD is set; the dashboard "
            "and /metrics are open to anyone who can reach this instance"
        )
    logger.info("TAP startup complete")
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await close_redis()
        logger.info("TAP shutdown complete")


app = FastAPI(title="TAP — Token Analytics Proxy", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Only needed when the dashboard is served from a different origin than the API;
# the bundled dashboard is same-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths that carry their own authentication, or none by design. Everything else
# — the dashboard, /metrics, the OpenAPI docs — sits behind the credentials in
# app.access once any are configured.
_PUBLIC_PREFIXES = ("/v1", "/health")


@app.middleware("http")
async def guard_private_surface(request: Request, call_next):
    if not request.url.path.startswith(_PUBLIC_PREFIXES) and not is_authorised(request):
        return Response(status_code=401, headers=UNAUTHORIZED_HEADERS)
    return await call_next(request)


app.include_router(proxy.router)
app.include_router(metrics.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up. Deliberately checks nothing else."""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness(response: Response) -> dict[str, str]:
    """Readiness: Postgres and Redis are both reachable.

    Every request writes a row and touches the rate-limit counters, so the app
    needs both to work. A probe that returned 200 with a dead database would
    keep a broken instance taking traffic.
    """
    checks: dict[str, str] = {}

    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception:
        logger.warning("readiness: database unreachable", exc_info=True)
        checks["database"] = "unavailable"

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        logger.warning("readiness: redis unreachable", exc_info=True)
        checks["redis"] = "unavailable"

    if any(state != "ok" for state in checks.values()):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", **checks}

    return {"status": "ok", **checks}


# The built dashboard, present in the production image and absent in
# development, where Vite serves it. Mounted last so it only catches paths no
# route claimed; html=True serves index.html for client-side routes.
_DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "static"

if _DASHBOARD_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_DASHBOARD_DIR, html=True), name="dashboard")
else:
    logger.info("no built dashboard at %s; serving API only", _DASHBOARD_DIR)
