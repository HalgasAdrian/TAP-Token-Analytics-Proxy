"""FastAPI application entrypoint.

Wires the transparent proxy and metrics routers, manages the shared
httpx client / DB / Redis lifecycle, and configures CORS + logging.

Security invariant: never log the Authorization header or any key material.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import metrics, proxy
from app.config import settings
from app.db import init_db
from app.redis_client import close_redis, redis_client

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage shared resources across the application lifespan."""
    # Startup: one shared httpx client, DB schema, Redis connectivity.
    app.state.http_client = httpx.AsyncClient(
        timeout=settings.upstream_timeout_seconds
    )
    await init_db()
    await redis_client.ping()
    logger.info("TAP startup complete")
    try:
        yield
    finally:
        # Shutdown: dispose of shared resources cleanly.
        await app.state.http_client.aclose()
        await close_redis()
        logger.info("TAP shutdown complete")


app = FastAPI(title="TAP — Token Analytics Proxy", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(proxy.router)
app.include_router(metrics.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
