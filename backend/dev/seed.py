"""Seed request_logs with synthetic traffic, for demos and for working on the
metrics queries without generating real load.

    docker compose exec api python -m dev.seed --hours 48 --requests 2000

Run as a module, not a path: `python dev/seed.py` would put `/app/dev` on
sys.path instead of `/app`, and the `app` imports below would fail.

Writes only to request_logs. Pass --truncate to clear existing rows first.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.cost import compute_cost
from app.db import AsyncSessionLocal
from app.models import RequestLog

# Traffic mix, roughly what a small app sends: mostly the cheap model.
_MODEL_WEIGHTS = {
    "gpt-4o-mini": 0.65,
    "gpt-4o": 0.20,
    "gpt-3.5-turbo": 0.15,
}

_CACHE_HIT_RATE = 0.24
_ERROR_RATE = 0.045

# Errors a gateway actually sees, and their relative frequency.
_ERROR_STATUSES = [(500, 0.4), (502, 0.3), (429, 0.2), (400, 0.1)]


def _weighted_choice(weights: dict[str, float]) -> str:
    roll = random.random()
    cumulative = 0.0
    for value, weight in weights.items():
        cumulative += weight
        if roll <= cumulative:
            return value
    return next(iter(weights))


def _error_status() -> int:
    roll = random.random()
    cumulative = 0.0
    for status, weight in _ERROR_STATUSES:
        cumulative += weight
        if roll <= cumulative:
            return status
    return 500


def _latency_ms(cache_hit: bool) -> float:
    """A right-skewed latency, so percentiles differ meaningfully.

    lognormvariate gives the long tail real LLM calls have; a uniform draw
    would make p50 and p95 nearly identical and the chart pointless.
    """
    if cache_hit:
        return round(random.uniform(0.6, 4.0), 2)
    return round(random.lognormvariate(6.4, 0.55), 2)


def _diurnal_weight(hour: int) -> float:
    """Busier during working hours, so volume has a shape."""
    return 0.35 + 0.65 * max(0.0, 1.0 - abs(hour - 14) / 11.0)


def _make_row(created_at: datetime) -> RequestLog:
    model = _weighted_choice(_MODEL_WEIGHTS)
    is_error = random.random() < _ERROR_RATE
    cache_hit = not is_error and random.random() < _CACHE_HIT_RATE

    prompt = "Summarise the following support ticket and suggest a next step."
    request_body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    if is_error:
        status_code = _error_status()
        return RequestLog(
            created_at=created_at,
            project_id=None,
            provider="openai",
            model=model,
            endpoint="/v1/chat/completions",
            status_code=status_code,
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
            latency_ms=_latency_ms(False),
            ttft_ms=None,
            cache_hit=False,
            request_body=request_body,
            response_body={"error": {"message": "synthetic failure"}},
            error=None if status_code < 500 else "upstream error",
        )

    input_tokens = random.randint(120, 2400)
    output_tokens = random.randint(40, 800)
    latency = _latency_ms(cache_hit)

    # A quarter of successful calls are streamed, so ttft_ms is populated for
    # some rows and null for others — as in real traffic.
    streamed = not cache_hit and random.random() < 0.25

    return RequestLog(
        created_at=created_at,
        project_id=None,
        provider="openai",
        model=model,
        endpoint="/v1/chat/completions",
        status_code=200,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=compute_cost(model, input_tokens, output_tokens),
        latency_ms=latency,
        ttft_ms=round(latency * random.uniform(0.15, 0.45), 2) if streamed else None,
        cache_hit=cache_hit,
        request_body=request_body,
        response_body={
            "model": model,
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        },
        error=None,
    )


async def seed(hours: int, requests: int, truncate: bool) -> None:
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=hours)

    # Distribute timestamps across the window, weighted by hour of day.
    weights = []
    for offset in range(hours):
        stamp = window_start + timedelta(hours=offset)
        weights.append(_diurnal_weight(stamp.hour))
    total_weight = sum(weights) or 1.0

    rows: list[RequestLog] = []
    for offset in range(hours):
        share = weights[offset] / total_weight
        count = max(1, round(requests * share))
        hour_start = window_start + timedelta(hours=offset)
        for _ in range(count):
            created_at = hour_start + timedelta(seconds=random.uniform(0, 3600))
            if created_at > now:
                continue
            rows.append(_make_row(created_at))

    async with AsyncSessionLocal() as session:
        if truncate:
            await session.execute(delete(RequestLog))
        session.add_all(rows)
        await session.commit()

    print(f"seeded {len(rows)} request_logs rows across the last {hours}h")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=48)
    parser.add_argument("--requests", type=int, default=2000)
    parser.add_argument("--truncate", action="store_true")
    args = parser.parse_args()

    asyncio.run(seed(args.hours, args.requests, args.truncate))


if __name__ == "__main__":
    main()
