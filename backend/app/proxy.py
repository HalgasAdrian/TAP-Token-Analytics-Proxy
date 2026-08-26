"""Transparent proxy for /v1/*.

Requests pass through auth, rate limiting, and the cache before being forwarded
upstream, buffered or streamed. Every forwarded call is written to request_logs.

The caller's Authorization header is relayed upstream unchanged but is never
logged, cached, or persisted.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
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
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_auth
from app.cache import cache_get, cache_key, cache_set
from app.config import settings
from app.cost import compute_cost
from app.db import get_session
from app.logging_sink import write_request_log
from app.providers import DEFAULT_PROVIDER, get_adapter
from app.rate_limit import check_rate_limit
from app.redis_client import get_redis

router = APIRouter()

# Recomputed by the HTTP client for the new request.
_STRIPPED_HEADERS: frozenset[str] = frozenset({"host", "content-length"})

_SSE_EVENT_DELIMITER = b"\n\n"

# Ceiling on the partial-event buffer, so an upstream that never emits a
# delimiter cannot exhaust memory.
_MAX_SSE_RESIDUAL_BYTES = 64 * 1024


def _filter_headers(headers: Any) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in _STRIPPED_HEADERS
    }


def _parse_json(raw: bytes) -> Any | None:
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
    ttft_ms: float | None = None,
) -> dict[str, Any]:
    """Assemble a request-log record, deriving token counts and cost.

    Token columns stay NULL unless the provider actually reported usage, which
    is meaningfully different from a genuine zero.
    """
    usage = None
    if isinstance(response_json, dict) and isinstance(response_json.get("usage"), dict):
        usage = get_adapter(provider).extract_usage(response_json)

    # The echoed-back model resolves an alias to the id that was billed.
    resolved_model = usage.model if usage is not None and usage.model else model

    return {
        "project_id": project_id,
        "provider": provider,
        "model": resolved_model,
        "endpoint": endpoint,
        "status_code": status_code,
        "input_tokens": usage.input_tokens if usage is not None else None,
        "output_tokens": usage.output_tokens if usage is not None else None,
        "cached_input_tokens": (
            usage.cached_input_tokens if usage is not None else None
        ),
        "cost_usd": (
            compute_cost(
                resolved_model or "",
                usage.input_tokens,
                usage.output_tokens,
                usage.cached_input_tokens,
            )
            if usage is not None
            else None
        ),
        "latency_ms": latency_ms,
        "ttft_ms": ttft_ms,
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
    handler_start = time.perf_counter()
    provider = DEFAULT_PROVIDER
    endpoint = request.url.path

    auth = None
    if settings.auth_enabled:
        auth = await require_auth(request, session)
    project_id = auth.project.id if auth is not None else None

    allowed = await check_rate_limit(
        redis,
        auth.api_key.id if auth is not None else None,
        auth.api_key.rate_limit if auth is not None else settings.default_rate_limit,
        settings.rate_limit_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )

    # Read the body once and reuse it for the cache key and the log record.
    body = await request.body()
    request_json = _parse_json(body)
    model = request_json.get("model") if isinstance(request_json, dict) else None

    if isinstance(request_json, dict) and request_json.get("stream"):
        return await stream_proxy(
            path,
            request,
            background_tasks,
            body=body,
            request_json=request_json,
            project_id=project_id,
            provider=provider,
            model=model,
            endpoint=endpoint,
        )

    cacheable = request.method == "POST" and isinstance(request_json, dict)
    ckey: str | None = None
    if cacheable:
        ckey = cache_key(request_json)
        cached = await cache_get(redis, ckey)
        if cached is not None:
            latency_ms = (time.perf_counter() - handler_start) * 1000.0
            background_tasks.add_task(
                write_request_log,
                _build_log_record(
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
                ),
            )
            return Response(
                content=json.dumps(cached),
                status_code=status.HTTP_200_OK,
                media_type="application/json",
            )

    client: httpx.AsyncClient = request.app.state.http_client
    upstream_url = get_adapter(provider).build_upstream_url(path)
    forward_headers = _filter_headers(request.headers)

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
        # Only the error class, never the request detail, which carries headers.
        error = f"upstream request failed: {exc.__class__.__name__}"
        background_tasks.add_task(
            write_request_log,
            _build_log_record(
                endpoint=endpoint,
                provider=provider,
                model=model,
                status_code=status.HTTP_502_BAD_GATEWAY,
                latency_ms=latency_ms,
                project_id=project_id,
                cache_hit=False,
                request_json=request_json,
                response_json=None,
                error=error,
            ),
        )
        return Response(
            content=json.dumps({"error": "upstream request failed"}),
            status_code=status.HTTP_502_BAD_GATEWAY,
            media_type="application/json",
        )

    response_json = _parse_json(upstream.content)

    if (
        cacheable
        and ckey is not None
        and upstream.status_code == status.HTTP_200_OK
        and response_json is not None
    ):
        await cache_set(redis, ckey, response_json, settings.cache_ttl_seconds)

    background_tasks.add_task(
        write_request_log,
        _build_log_record(
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
        ),
    )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


class _SseUsageWatcher:
    """Observes an SSE stream in flight without retaining it.

    A streamed completion reports usage only in a trailing chunk, so telemetry
    needs the end of the stream while buffering none of it. Chunk boundaries do
    not align with event boundaries, hence the residual buffer.
    """

    __slots__ = ("_residual", "usage_envelope", "ttft_ms", "_start")

    def __init__(self, start: float) -> None:
        self._residual = b""
        self._start = start
        self.usage_envelope: dict[str, Any] | None = None
        self.ttft_ms: float | None = None

    def feed(self, chunk: bytes) -> None:
        self._residual += chunk
        while _SSE_EVENT_DELIMITER in self._residual:
            raw_event, self._residual = self._residual.split(_SSE_EVENT_DELIMITER, 1)
            self._consume(raw_event)

        if len(self._residual) > _MAX_SSE_RESIDUAL_BYTES:
            self._residual = self._residual[-_MAX_SSE_RESIDUAL_BYTES:]

    def _consume(self, raw_event: bytes) -> None:
        for line in raw_event.split(b"\n"):
            if not line.startswith(b"data:"):
                continue
            payload = line[len(b"data:") :].strip()
            if not payload or payload == b"[DONE]":
                continue
            try:
                parsed = json.loads(payload)
            except ValueError:
                continue
            if not isinstance(parsed, dict):
                continue

            # Keep the latest: some providers send interim usage chunks.
            if isinstance(parsed.get("usage"), dict):
                self.usage_envelope = parsed

            if self.ttft_ms is None and _has_content_delta(parsed):
                self.ttft_ms = (time.perf_counter() - self._start) * 1000.0


def _has_content_delta(chunk: dict[str, Any]) -> bool:
    """True when a chunk carries generated text.

    The opening chunk announces the assistant role with an empty string;
    counting it would understate time-to-first-token.
    """
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    first = choices[0]
    if not isinstance(first, dict):
        return False
    delta = first.get("delta")
    if not isinstance(delta, dict):
        return False
    return bool(delta.get("content"))


async def stream_proxy(
    path: str,
    request: Request,
    background_tasks: BackgroundTasks,
    *,
    body: bytes,
    request_json: Any | None,
    project_id: int | None,
    provider: str,
    model: str | None,
    endpoint: str,
) -> Response:
    """Relay an upstream SSE response incrementally, recording TTFT.

    The cache is bypassed: an SSE body is not interchangeable with a buffered
    one, and replaying a stored stream would report a fabricated TTFT.
    """
    client: httpx.AsyncClient = request.app.state.http_client
    upstream_url = get_adapter(provider).build_upstream_url(path)
    forward_headers = _filter_headers(request.headers)

    start = time.perf_counter()
    stream_context = client.stream(
        request.method,
        upstream_url,
        content=body,
        params=list(request.query_params.multi_items()),
        headers=forward_headers,
    )

    # Entered manually because the status code is needed to build the response
    # before the body flows, and the context must outlive this function. The
    # relay generator closes it.
    try:
        upstream = await stream_context.__aenter__()
    except httpx.HTTPError as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        background_tasks.add_task(
            write_request_log,
            _build_log_record(
                endpoint=endpoint,
                provider=provider,
                model=model,
                status_code=status.HTTP_502_BAD_GATEWAY,
                latency_ms=latency_ms,
                project_id=project_id,
                cache_hit=False,
                request_json=request_json,
                response_json=None,
                error=f"upstream stream failed: {exc.__class__.__name__}",
            ),
        )
        return Response(
            content=json.dumps({"error": "upstream request failed"}),
            status_code=status.HTTP_502_BAD_GATEWAY,
            media_type="application/json",
        )

    watcher = _SseUsageWatcher(start)

    async def relay() -> AsyncIterator[bytes]:
        error: str | None = None
        try:
            async for chunk in upstream.aiter_bytes():
                watcher.feed(chunk)
                yield chunk
        except httpx.HTTPError as exc:
            error = f"upstream stream interrupted: {exc.__class__.__name__}"
        finally:
            await stream_context.__aexit__(None, None, None)
            # Awaited here rather than deferred to a background task, which
            # would be collected too late to run. response_body is the trailing
            # usage envelope; the deltas are not retained.
            await write_request_log(
                _build_log_record(
                    endpoint=endpoint,
                    provider=provider,
                    model=model,
                    status_code=upstream.status_code,
                    latency_ms=(time.perf_counter() - start) * 1000.0,
                    project_id=project_id,
                    cache_hit=False,
                    request_json=request_json,
                    response_json=watcher.usage_envelope,
                    error=error,
                    ttft_ms=watcher.ttft_ms,
                )
            )

    return StreamingResponse(
        relay(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "text/event-stream"),
    )
