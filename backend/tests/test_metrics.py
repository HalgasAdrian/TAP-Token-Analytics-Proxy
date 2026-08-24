"""Aggregation tests.

Values are chosen so every expected number is arithmetic a reader can verify,
rather than a figure copied back out of the implementation.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.metrics import (
    query_cache_hit_rate,
    query_cost_by_model,
    query_error_rate,
    query_latency_percentiles,
    query_volume,
)
from app.models import RequestLog

BASE = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


async def add_rows(session, rows: list[dict]) -> None:
    defaults = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "endpoint": "/v1/chat/completions",
        "status_code": 200,
        "latency_ms": 100.0,
        "cache_hit": False,
        "request_body": {},
    }
    session.add_all([RequestLog(**{**defaults, **row}) for row in rows])
    await session.commit()


# --- no rows -----------------------------------------------------------


async def test_no_rows_returns_empty_series(session):
    assert await query_volume(session) == []
    assert await query_cost_by_model(session) == []
    assert await query_latency_percentiles(session) == []


async def test_no_rows_returns_zeroed_ratios(session):
    cache = await query_cache_hit_rate(session)
    assert cache == {
        "total": 0,
        "hits": 0,
        "misses": 0,
        "hit_rate": 0.0,
        "series": [],
    }

    errors = await query_error_rate(session)
    assert errors == {"total": 0, "errors": 0, "error_rate": 0.0, "series": []}


# --- volume -----------------------------------------------------------------


async def test_volume_counts_per_bucket_oldest_first(session):
    await add_rows(
        session,
        [
            {"created_at": BASE},
            {"created_at": BASE + timedelta(minutes=10)},
            {"created_at": BASE + timedelta(hours=1)},
            {"created_at": BASE + timedelta(hours=3)},
        ],
    )

    result = await query_volume(session, bucket="hour")

    assert [row["count"] for row in result] == [2, 1, 1]
    assert result[0]["bucket"] < result[1]["bucket"] < result[2]["bucket"]


async def test_volume_regroups_at_a_coarser_granularity(session):
    await add_rows(
        session,
        [
            {"created_at": BASE},
            {"created_at": BASE + timedelta(hours=5)},
            {"created_at": BASE + timedelta(days=2)},
        ],
    )

    assert [row["count"] for row in await query_volume(session, bucket="day")] == [2, 1]


async def test_window_is_half_open(session):
    await add_rows(
        session,
        [
            {"created_at": BASE},
            {"created_at": BASE + timedelta(hours=1)},
            {"created_at": BASE + timedelta(hours=2)},
        ],
    )

    result = await query_volume(
        session,
        start=BASE,
        end=BASE + timedelta(hours=2),
        bucket="hour",
    )

    # start is inclusive, end exclusive: the 14:00 row is outside.
    assert [row["count"] for row in result] == [1, 1]


async def test_unsupported_bucket_is_rejected(session):
    for query in (query_volume, query_latency_percentiles, query_cache_hit_rate):
        with pytest.raises(HTTPException) as raised:
            await query(session, bucket="fortnight")
        assert raised.value.status_code == 400


# --- cost by model ----------------------------------------------------------


async def test_cost_by_model_groups_sums_and_orders_by_spend(session):
    await add_rows(
        session,
        [
            {
                "created_at": BASE,
                "model": "gpt-4o-mini",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.001,
            },
            {
                "created_at": BASE,
                "model": "gpt-4o-mini",
                "input_tokens": 200,
                "output_tokens": 25,
                "cost_usd": 0.002,
            },
            {
                "created_at": BASE,
                "model": "gpt-4o",
                "input_tokens": 10,
                "output_tokens": 5,
                "cost_usd": 0.05,
            },
        ],
    )

    result = await query_cost_by_model(session)

    assert [row["model"] for row in result] == ["gpt-4o", "gpt-4o-mini"]
    mini = result[1]
    assert mini["requests"] == 2
    assert mini["input_tokens"] == 300
    assert mini["output_tokens"] == 75
    assert mini["cost_usd"] == pytest.approx(0.003)


async def test_a_model_whose_calls_all_failed_reports_zero_not_null(session):
    await add_rows(
        session,
        [
            {
                "created_at": BASE,
                "model": "gpt-4o",
                "status_code": 500,
                "input_tokens": None,
                "output_tokens": None,
                "cost_usd": None,
            }
        ],
    )

    row = (await query_cost_by_model(session))[0]

    assert (row["cost_usd"], row["input_tokens"], row["output_tokens"]) == (0.0, 0, 0)
    assert row["requests"] == 1


async def test_rows_without_a_model_are_labelled_unknown(session):
    await add_rows(session, [{"created_at": BASE, "model": None, "cost_usd": 0.01}])

    assert (await query_cost_by_model(session))[0]["model"] == "unknown"


# --- latency ----------------------------------------------------------------


async def test_percentiles_are_interpolated(session):
    await add_rows(
        session,
        [
            {"created_at": BASE, "latency_ms": value}
            for value in (100.0, 200.0, 300.0, 400.0, 500.0)
        ],
    )

    row = (await query_latency_percentiles(session, bucket="hour"))[0]

    # percentile_cont over 5 sorted values: p50 lands on 300 exactly; p95 sits
    # 0.8 of the way from 400 to 500.
    assert row["p50"] == pytest.approx(300.0)
    assert row["p95"] == pytest.approx(480.0)
    assert row["count"] == 5


async def test_a_single_row_reports_it_as_both_percentiles(session):
    await add_rows(session, [{"created_at": BASE, "latency_ms": 42.0}])

    row = (await query_latency_percentiles(session, bucket="hour"))[0]
    assert (row["p50"], row["p95"]) == (42.0, 42.0)


async def test_percentiles_are_computed_per_bucket(session):
    await add_rows(
        session,
        [
            {"created_at": BASE, "latency_ms": 10.0},
            {"created_at": BASE + timedelta(hours=1), "latency_ms": 1000.0},
        ],
    )

    result = await query_latency_percentiles(session, bucket="hour")

    assert [row["p50"] for row in result] == [10.0, 1000.0]


# --- cache hit rate ---------------------------------------------------------


async def test_hit_rate_and_series_agree(session):
    await add_rows(
        session,
        [
            {"created_at": BASE, "cache_hit": True},
            {"created_at": BASE, "cache_hit": True},
            {"created_at": BASE, "cache_hit": False},
            {"created_at": BASE + timedelta(hours=1), "cache_hit": False},
        ],
    )

    result = await query_cache_hit_rate(session, bucket="hour")

    assert (result["total"], result["hits"], result["misses"]) == (4, 2, 2)
    assert result["hit_rate"] == pytest.approx(0.5)
    assert result["series"][0]["hit_rate"] == pytest.approx(2 / 3)
    assert result["series"][1]["hit_rate"] == 0.0
    assert sum(bucket["hits"] for bucket in result["series"]) == result["hits"]


# --- error rate -------------------------------------------------------------


async def test_error_rate_counts_non_2xx(session):
    await add_rows(
        session,
        [
            {"created_at": BASE, "status_code": 200},
            {"created_at": BASE, "status_code": 200},
            {"created_at": BASE, "status_code": 400},
            {"created_at": BASE, "status_code": 500},
        ],
    )

    result = await query_error_rate(session, bucket="hour")

    assert (result["total"], result["errors"]) == (4, 2)
    assert result["error_rate"] == pytest.approx(0.5)


async def test_a_transport_failure_counts_as_an_error(session):
    # A request that never reached the upstream is recorded with `error` set.
    await add_rows(
        session,
        [
            {"created_at": BASE, "status_code": 200},
            {"created_at": BASE, "status_code": 200, "error": "upstream timeout"},
        ],
    )

    assert (await query_error_rate(session, bucket="hour"))["errors"] == 1


async def test_a_3xx_is_not_an_error(session):
    await add_rows(session, [{"created_at": BASE, "status_code": 304}])

    assert (await query_error_rate(session, bucket="hour"))["errors"] == 0
