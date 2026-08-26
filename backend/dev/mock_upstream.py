"""A fake OpenAI-compatible upstream for local development and tests.

Point TAP at it to exercise the whole pipeline with no API key and no provider
spend: UPSTREAM_BASE_URL=http://mock-upstream:9000

Runs only under Compose's `dev` profile; it is not part of the application
package or the production image.

Testing hooks: a model prefixed `fail-` returns 500, one prefixed `slow-` adds
latency, one prefixed `cached-` reports half its prompt as a prompt-cache hit,
and `stream: true` emits SSE ending with a usage chunk.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Mock OpenAI-compatible upstream")

# Jitter gives latency percentiles a distribution rather than a single spike.
MOCK_BASE_MS = float(os.getenv("MOCK_BASE_MS", "40"))
MOCK_JITTER_MS = float(os.getenv("MOCK_JITTER_MS", "120"))
MOCK_SLOW_MS = float(os.getenv("MOCK_SLOW_MS", "900"))

_REPLY = (
    "This is a synthetic completion from TAP's mock upstream. "
    "No provider was contacted and no tokens were billed."
)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token, at least 1."""
    return max(1, len(text) // 4)


def _prompt_tokens(payload: dict) -> int:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return 1
    total = 0
    for message in messages:
        if isinstance(message, dict):
            total += _estimate_tokens(str(message.get("content") or ""))
    return max(1, total)


def _usage(model: str, prompt_tokens: int, completion_tokens: int) -> dict:
    """Usage block, with a prompt-cache detail for `cached-` models."""
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if model.startswith("cached-"):
        usage["prompt_tokens_details"] = {"cached_tokens": prompt_tokens // 2}
    return usage


async def _simulate_latency(model: str) -> None:
    delay_ms = MOCK_BASE_MS + random.random() * MOCK_JITTER_MS
    if model.startswith("slow-"):
        delay_ms += MOCK_SLOW_MS
    await asyncio.sleep(delay_ms / 1000.0)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> object:
    payload = await request.json()
    if not isinstance(payload, dict):
        payload = {}

    model = str(payload.get("model") or "gpt-4o-mini")
    await _simulate_latency(model)

    if model.startswith("fail-"):
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": f"mock upstream failure for model {model}",
                    "type": "server_error",
                    "code": None,
                }
            },
        )

    prompt_tokens = _prompt_tokens(payload)
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if payload.get("stream"):
        return StreamingResponse(
            _stream_chunks(completion_id, created, model, prompt_tokens),
            media_type="text/event-stream",
        )

    completion_tokens = _estimate_tokens(_REPLY)
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": _REPLY},
                "finish_reason": "stop",
            }
        ],
        "usage": _usage(model, prompt_tokens, completion_tokens),
    }


async def _stream_chunks(
    completion_id: str, created: int, model: str, prompt_tokens: int
) -> AsyncIterator[str]:
    """Emit an OpenAI-shaped SSE stream with usage last."""

    def envelope(delta: dict, finish_reason: str | None = None) -> str:
        chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        return f"data: {json.dumps(chunk)}\n\n"

    yield envelope({"role": "assistant", "content": ""})

    words = _REPLY.split(" ")
    for index, word in enumerate(words):
        await asyncio.sleep(0.02)
        text = word if index == 0 else f" {word}"
        yield envelope({"content": text})

    yield envelope({}, finish_reason="stop")

    usage_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [],
        "usage": _usage(model, prompt_tokens, _estimate_tokens(_REPLY)),
    }
    yield f"data: {json.dumps(usage_chunk)}\n\n"
    yield "data: [DONE]\n\n"


@app.get("/v1/models")
async def list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "owned_by": "mock"}
            for name in ("gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo")
        ],
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "upstream": "mock"}
