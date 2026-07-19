"""Transparent proxy router for TAP.

This module implements a single transparent, buffered forward route that relays
requests to the configured upstream provider. All feature integrations
(auth, rate limiting, caching, request logging) are guarded behind their
settings flags, which default to OFF, so the base proxy runs before any
assignment (A1/A2/A5/A6) is implemented.

Security invariant: the caller's ``Authorization`` header (and any key
material) is relayed upstream unchanged but is NEVER logged, cached, or
persisted. Only request/response bodies and non-sensitive metadata are ever
recorded.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_project
from app.cache import cache_get, cache_key, cache_set
from app.config import settings
from app.db import get_session
from app.logging_sink import write_request_log
from app.rate_limit import check_rate_limit
from app.redis_client import get_redis

router = APIRouter()

# Headers that must not be relayed verbatim to the upstream (compared
# case-insensitively). ``host`` and ``content-length`` are recomputed by the
# HTTP client for the new request.
_STRIPPED_HEADERS: frozenset[str] = frozenset({"host", "content-length"})


def _filter_headers(headers: Any) -> dict[str, str]:
    """Copy request headers to relay upstream, dropping hop-by-hop entries.

    The caller's ``Authorization`` header is intentionally preserved
    (pass-through auth) but is never logged elsewhere.
    """
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in _STRIPPED_HEADERS
    }


def _parse_json(raw: bytes) -> Any | None:
    """Best-effort JSON parse; returns ``None`` when the bytes are not JSON."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _build_log_record(
    *,
    endpoint: str,
    provider: str,
    model: str | None,
    status_code: int,
    latency_ms: float,
    project_id: int | None,
    cache_hit: bool,
    request_json: Any | None,
    response_json: Any | None,
    error: str | None,
) -> dict[str, Any]:
    """Assemble a request-log record.

    Never contains the ``Authorization`` header, API keys, or any other key
    material — only the request/response payloads and derived metadata.
    """
    return {
        "project_id": project_id,
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "status_code": status_code,
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": None,
        "latency_ms": latency_ms,
        "ttft_ms": None,
        "cache_hit": cache_hit,
        "request_body": request_json if isinstance(request_json, dict) else {},
        "response_body": response_json,
        "error": error,
    }


@router.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy(
    path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis),
) -> Response:
    """Transparent buffered forward of ``/v1/*`` to the upstream provider."""
    handler_start = time.perf_counter()
    provider = "openai"
    endpoint = request.url.path

    # ------------------------------------------------------------------
    # 1. Auth (A1) — resolve the owning project when enabled; otherwise the
    #    proxy is pass-through and ``project`` stays None. Called inline so the
    #    unimplemented stub can never run while AUTH_ENABLED is false.
    # ------------------------------------------------------------------
    project = None
    if settings.auth_enabled:
        project = await require_project(request, session)
    project_id = project.id if project is not None else None

    # ------------------------------------------------------------------
    # 2. Rate limit (A6) — reject with HTTP 429 when the project is over quota.
    # ------------------------------------------------------------------
    if settings.rate_limit_enabled:
        allowed = await check_rate_limit(
            redis,
            project_id,
            settings.default_rate_limit,
            settings.rate_limit_window_seconds,
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )

    # Read the client body exactly once; reuse for the cache key and the log
    # record. Headers (which carry auth) are never placed into the record.
    body = await request.body()
    request_json = _parse_json(body)
    model = (
        request_json.get("model") if isinstance(request_json, dict) else None
    )

    # ------------------------------------------------------------------
    # 3. Cache (A5) — look up before forwarding; only attempt for POST requests
    #    carrying a JSON object body (the idempotent/completion case). The
    #    temperature / non-deterministic policy lives inside cache_key (A5).
    # ------------------------------------------------------------------
    cacheable = (
        settings.cache_enabled
        and request.method == "POST"
        and isinstance(request_json, dict)
    )
    ckey: str | None = None
    if cacheable:
        ckey = cache_key(request_json)
        cached = await cache_get(redis, ckey)
        if cached is not None:
            latency_ms = (time.perf_counter() - handler_start) * 1000.0
            response = Response(
                content=json.dumps(cached),
                status_code=status.HTTP_200_OK,
                media_type="application/json",
            )
            if settings.logging_enabled:
                record = _build_log_record(
                    endpoint=endpoint,
                    provider=provider,
                    model=model,
                    status_code=status.HTTP_200_OK,
                    latency_ms=latency_ms,
                    project_id=project_id,
                    cache_hit=True,
                    request_json=request_json,
                    response_json=cached,
                    error=None,
                )
                background_tasks.add_task(write_request_log, record)
            return response

    # ------------------------------------------------------------------
    # Buffered forward to upstream using the shared client. Latency is measured
    # with perf_counter() around the upstream call only.
    # ------------------------------------------------------------------
    client: httpx.AsyncClient = request.app.state.http_client
    upstream_url = f"{settings.upstream_base_url}/v1/{path}"
    forward_headers = _filter_headers(request.headers)

    error: str | None = None
    upstream: httpx.Response | None = None
    start = time.perf_counter()
    try:
        upstream = await client.request(
            request.method,
            upstream_url,
            content=body,
            params=list(request.query_params.multi_items()),
            headers=forward_headers,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0
    except httpx.HTTPError as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        # Redact: never surface header/key material. httpx error strings only
        # reference the request line and error class.
        error = f"upstream request failed: {exc.__class__.__name__}"
        status_code = status.HTTP_502_BAD_GATEWAY
        response = Response(
            content=json.dumps({"error": "upstream request failed"}),
            status_code=status_code,
            media_type="application/json",
        )
        if settings.logging_enabled:
            record = _build_log_record(
                endpoint=endpoint,
                provider=provider,
                model=model,
                status_code=status_code,
                latency_ms=latency_ms,
                project_id=project_id,
                cache_hit=False,
                request_json=request_json,
                response_json=None,
                error=error,
            )
            background_tasks.add_task(write_request_log, record)
        return response

    response = Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )

    # ------------------------------------------------------------------
    # 3b. Cache store (A5) — populate on a successful, JSON-parseable miss.
    # ------------------------------------------------------------------
    response_json = _parse_json(upstream.content)
    if (
        cacheable
        and ckey is not None
        and upstream.status_code == status.HTTP_200_OK
        and response_json is not None
    ):
        await cache_set(redis, ckey, response_json, settings.cache_ttl_seconds)

    # ------------------------------------------------------------------
    # 4. Logging (A2) — persist telemetry in a background task after responding.
    #    The record never contains Authorization/key material.
    # ------------------------------------------------------------------
    if settings.logging_enabled:
        record = _build_log_record(
            endpoint=endpoint,
            provider=provider,
            model=model,
            status_code=upstream.status_code,
            latency_ms=latency_ms,
            project_id=project_id,
            cache_hit=False,
            request_json=request_json,
            response_json=response_json,
            error=None,
        )
        background_tasks.add_task(write_request_log, record)

    return response


async def stream_proxy(
    path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    redis=Depends(get_redis),
) -> Response:
    """Streamed passthrough (A8). Present but NOT wired into the default path."""
    # ============================================================
    # ASSIGNMENT: A8 streaming passthrough
    # ------------------------------------------------------------
    # Implement: stream an upstream SSE response back to the caller with
    #            httpx.AsyncClient.stream(...) + StreamingResponse, measuring TTFT,
    #            without buffering the whole body.
    # Why:       supports stream=true chat completions; the buffered path stays the default.
    # Done when: a stream=true request relays chunks incrementally and records ttft_ms.
    # Reference: https://www.python-httpx.org/async/
    #            https://fastapi.tiangolo.com/advanced/custom-response/
    #            https://platform.openai.com/docs/api-reference/chat/streaming
    # ============================================================
    raise NotImplementedError("ASSIGNMENT: A8 streaming passthrough")
