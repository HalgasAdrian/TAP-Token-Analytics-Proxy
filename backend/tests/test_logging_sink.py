from sqlalchemy import func, select

from app.logging_sink import write_request_log
from app.models import RequestLog


def record(**overrides) -> dict:
    base = {
        "project_id": None,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "endpoint": "/v1/chat/completions",
        "status_code": 200,
        "input_tokens": 120,
        "output_tokens": 34,
        "cost_usd": 0.000038,
        "latency_ms": 412.5,
        "ttft_ms": None,
        "cache_hit": False,
        "request_body": {"model": "gpt-4o-mini"},
        "response_body": {"id": "chatcmpl-1"},
        "error": None,
    }
    return {**base, **overrides}


async def count_rows(session) -> int:
    return await session.scalar(select(func.count()).select_from(RequestLog))


async def test_a_row_is_written(session):
    await write_request_log(record())

    row = (await session.execute(select(RequestLog))).scalar_one()
    assert row.model == "gpt-4o-mini"
    assert row.input_tokens == 120
    assert row.cache_hit is False
    assert row.created_at is not None


async def test_unexpected_keys_are_ignored_rather_than_raising(session):
    await write_request_log(record(not_a_column="x", another=1))

    assert await count_rows(session) == 1


async def test_a_failed_write_does_not_raise(session):
    # latency_ms is NOT NULL, so this insert must fail at the database.
    await write_request_log(record(latency_ms=None))

    assert await count_rows(session) == 0


async def test_a_failed_write_does_not_poison_later_writes(session):
    await write_request_log(record(latency_ms=None))
    await write_request_log(record())

    assert await count_rows(session) == 1


async def test_nullable_telemetry_is_preserved_as_null(session):
    await write_request_log(
        record(input_tokens=None, output_tokens=None, cost_usd=None, error="boom")
    )

    row = (await session.execute(select(RequestLog))).scalar_one()
    assert row.input_tokens is None
    assert row.cost_usd is None
    assert row.error == "boom"


async def test_streamed_rows_carry_ttft(session):
    await write_request_log(record(ttft_ms=87.5))

    row = (await session.execute(select(RequestLog))).scalar_one()
    assert row.ttft_ms == 87.5
