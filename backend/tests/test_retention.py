from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.logging_sink import _cap_body, write_request_log
from app.models import RequestLog
from app.retention import prune_request_logs


async def add_row(session, created_at: datetime) -> None:
    session.add(
        RequestLog(
            created_at=created_at,
            provider="openai",
            model="gpt-4o-mini",
            endpoint="/v1/chat/completions",
            status_code=200,
            latency_ms=100.0,
            cache_hit=False,
            request_body={},
        )
    )
    await session.commit()


async def row_count(session) -> int:
    return await session.scalar(select(func.count()).select_from(RequestLog))


# --- pruning ----------------------------------------------------------------


async def test_rows_past_the_window_are_deleted(session):
    now = datetime.now(UTC)
    await add_row(session, now - timedelta(days=40))
    await add_row(session, now - timedelta(days=31))
    await add_row(session, now - timedelta(days=1))

    deleted, _ = await prune_request_logs(30)

    assert deleted == 2
    assert await row_count(session) == 1


async def test_a_dry_run_reports_without_deleting(session):
    await add_row(session, datetime.now(UTC) - timedelta(days=40))

    matched, _ = await prune_request_logs(30, dry_run=True)

    assert matched == 1
    assert await row_count(session) == 1


async def test_nothing_is_deleted_when_all_rows_are_recent(session):
    await add_row(session, datetime.now(UTC))

    deleted, _ = await prune_request_logs(30)

    assert deleted == 0
    assert await row_count(session) == 1


async def test_a_non_positive_window_is_refused(session):
    for value in (0, -1):
        with pytest.raises(ValueError):
            await prune_request_logs(value)


async def test_the_cutoff_matches_the_requested_window(session):
    _, cutoff = await prune_request_logs(7, dry_run=True)

    assert abs((datetime.now(UTC) - cutoff).days - 7) <= 1


# --- body caps --------------------------------------------------------------


def test_a_small_body_is_stored_verbatim():
    body = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}
    assert _cap_body(body, 16384) is body


def test_an_oversized_body_becomes_a_size_marker():
    body = {"messages": [{"role": "user", "content": "x" * 50_000}]}

    capped = _cap_body(body, 1024)

    assert capped["_truncated"] is True
    assert capped["bytes"] > 50_000


def test_a_zero_limit_disables_capping():
    body = {"content": "x" * 50_000}
    assert _cap_body(body, 0) is body


def test_a_null_body_is_left_alone():
    assert _cap_body(None, 1024) is None


async def test_an_oversized_body_is_capped_on_write(session):
    settings.max_body_bytes = 512

    await write_request_log(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "endpoint": "/v1/chat/completions",
            "status_code": 200,
            "latency_ms": 100.0,
            "cache_hit": False,
            "request_body": {"prompt": "x" * 5000},
            "response_body": {"completion": "y" * 5000},
        }
    )

    row = (await session.execute(select(RequestLog))).scalar_one()
    assert row.request_body["_truncated"] is True
    assert row.response_body["_truncated"] is True
    # The row itself survives, so metrics still count the call.
    assert row.status_code == 200
