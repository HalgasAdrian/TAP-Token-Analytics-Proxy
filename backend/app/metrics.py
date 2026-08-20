"""Metrics API — aggregates `request_logs` into dashboard-ready JSON.

Every metric is a query over the ledger; nothing is stored pre-aggregated, so
the numbers cannot drift from the rows they summarise.

Scope note: the ledger records *forwarded* traffic. Requests rejected at the
auth or rate-limit gate short-circuit before the logging stage, so a 429 storm
does not appear here — deliberately, since writing a row per rejected request
would turn a flood into unbounded database growth. "Error rate" therefore means
errors among admitted requests.

Security invariant: nothing here reads, returns, or logs the Authorization
header or key material — only aggregated telemetry from `request_logs`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import RequestLog

router = APIRouter(prefix="/metrics")

# Granularities accepted by the `bucket` query param. Restricted to an explicit
# set so a typo is a 400 rather than a confusing empty result, and so the value
# handed to date_trunc is always one TAP chose.
_ALLOWED_BUCKETS: frozenset[str] = frozenset(
    {"minute", "hour", "day", "week", "month"}
)


def _validate_bucket(bucket: str) -> str:
    if bucket not in _ALLOWED_BUCKETS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unsupported bucket {bucket!r}; "
                f"expected one of {sorted(_ALLOWED_BUCKETS)}"
            ),
        )
    return bucket


def _in_window(
    statement: Select, start: datetime | None, end: datetime | None
) -> Select:
    """Constrain a statement to [start, end).

    Half-open so that adjacent windows neither overlap nor drop a row on the
    boundary. Either bound may be omitted to leave that side unbounded.
    """
    if start is not None:
        statement = statement.where(RequestLog.created_at >= start)
    if end is not None:
        statement = statement.where(RequestLog.created_at < end)
    return statement


def _bucket_column(bucket: str):
    """A date_trunc expression over created_at, labelled `bucket`.

    `bucket` is passed as a bind parameter, not interpolated into the SQL.
    """
    return func.date_trunc(bucket, RequestLog.created_at).label("bucket")


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _ratio(numerator: int, denominator: int) -> float:
    """Share of `denominator` accounted for by `numerator`, 0.0 when empty."""
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


# An "error" is any non-2xx/3xx response, or a request that never reached the
# upstream (transport failure, recorded with `error` set).
_IS_ERROR = (RequestLog.status_code >= 400) | (RequestLog.error.is_not(None))


# ---------------------------------------------------------------------------
# Routes (implemented boilerplate — wiring only)
# ---------------------------------------------------------------------------


@router.get("/volume")
async def get_volume(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    bucket: str = Query(default="hour"),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Request volume over time, bucketed by `bucket`."""
    return await query_volume(session, start=start, end=end, bucket=bucket)


@router.get("/cost-by-model")
async def get_cost_by_model(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Total USD cost and token counts grouped by model."""
    return await query_cost_by_model(session, start=start, end=end)


@router.get("/latency")
async def get_latency(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    bucket: str = Query(default="hour"),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Latency percentiles over time, bucketed by `bucket`."""
    return await query_latency_percentiles(
        session, start=start, end=end, bucket=bucket
    )


@router.get("/cache")
async def get_cache(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    bucket: str = Query(default="hour"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Cache-hit rate over the selected window."""
    return await query_cache_hit_rate(session, start=start, end=end, bucket=bucket)


@router.get("/errors")
async def get_errors(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    bucket: str = Query(default="hour"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Error rate over the selected window."""
    return await query_error_rate(session, start=start, end=end, bucket=bucket)


# ---------------------------------------------------------------------------
# Aggregation functions
# ---------------------------------------------------------------------------


async def query_volume(
    session: AsyncSession,
    start: datetime | None = None,
    end: datetime | None = None,
    bucket: str = "hour",
) -> list[dict[str, Any]]:
    """Request count per time bucket, oldest first."""
    _validate_bucket(bucket)
    bucket_column = _bucket_column(bucket)

    statement = _in_window(
        select(bucket_column, func.count().label("count")), start, end
    ).group_by(bucket_column).order_by(bucket_column)

    rows = (await session.execute(statement)).all()
    return [
        {"bucket": _isoformat(row.bucket), "count": int(row.count)}
        for row in rows
    ]


async def query_cost_by_model(
    session: AsyncSession,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, Any]]:
    """Spend and token totals per model, most expensive first.

    Token and cost columns are NULL for calls that reported no usage (errors,
    or providers that omit it), so each sum is coalesced — otherwise a model
    whose every call failed would return NULL rather than zero.
    """
    model = func.coalesce(RequestLog.model, "unknown").label("model")
    cost = func.coalesce(func.sum(RequestLog.cost_usd), 0.0).label("cost_usd")

    statement = _in_window(
        select(
            model,
            func.count().label("requests"),
            func.coalesce(func.sum(RequestLog.input_tokens), 0).label(
                "input_tokens"
            ),
            func.coalesce(func.sum(RequestLog.output_tokens), 0).label(
                "output_tokens"
            ),
            cost,
        ),
        start,
        end,
    ).group_by(model).order_by(cost.desc())

    rows = (await session.execute(statement)).all()
    return [
        {
            "model": row.model,
            "requests": int(row.requests),
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
            # Sub-cent sums carry float noise; 6 decimals is well below the
            # smallest meaningful unit while keeping the JSON readable.
            "cost_usd": round(float(row.cost_usd), 6),
        }
        for row in rows
    ]


async def query_latency_percentiles(
    session: AsyncSession,
    start: datetime | None = None,
    end: datetime | None = None,
    bucket: str = "hour",
) -> list[dict[str, Any]]:
    """Median and p95 latency per time bucket.

    Uses `percentile_cont`, which interpolates between observations, rather
    than a mean — tail latency is what a caller actually experiences, and an
    average hides it.
    """
    _validate_bucket(bucket)
    bucket_column = _bucket_column(bucket)

    statement = _in_window(
        select(
            bucket_column,
            func.percentile_cont(0.5)
            .within_group(RequestLog.latency_ms.asc())
            .label("p50"),
            func.percentile_cont(0.95)
            .within_group(RequestLog.latency_ms.asc())
            .label("p95"),
            func.count().label("count"),
        ),
        start,
        end,
    ).group_by(bucket_column).order_by(bucket_column)

    rows = (await session.execute(statement)).all()
    return [
        {
            "bucket": _isoformat(row.bucket),
            "p50": round(float(row.p50), 2) if row.p50 is not None else None,
            "p95": round(float(row.p95), 2) if row.p95 is not None else None,
            "count": int(row.count),
        }
        for row in rows
    ]


async def query_cache_hit_rate(
    session: AsyncSession,
    start: datetime | None = None,
    end: datetime | None = None,
    bucket: str = "hour",
) -> dict[str, Any]:
    """Cache-hit rate for the window, plus a per-bucket series.

    Returns both so a caller gets the headline number and its trend from one
    request; the totals are folded from the same rows, so they always agree.
    """
    _validate_bucket(bucket)
    bucket_column = _bucket_column(bucket)

    hits = func.count().filter(RequestLog.cache_hit.is_(True)).label("hits")

    statement = _in_window(
        select(bucket_column, func.count().label("total"), hits), start, end
    ).group_by(bucket_column).order_by(bucket_column)

    rows = (await session.execute(statement)).all()

    series = []
    total_count = 0
    total_hits = 0
    for row in rows:
        row_total = int(row.total)
        row_hits = int(row.hits)
        total_count += row_total
        total_hits += row_hits
        series.append(
            {
                "bucket": _isoformat(row.bucket),
                "total": row_total,
                "hits": row_hits,
                "misses": row_total - row_hits,
                "hit_rate": _ratio(row_hits, row_total),
            }
        )

    return {
        "total": total_count,
        "hits": total_hits,
        "misses": total_count - total_hits,
        "hit_rate": _ratio(total_hits, total_count),
        "series": series,
    }


async def query_error_rate(
    session: AsyncSession,
    start: datetime | None = None,
    end: datetime | None = None,
    bucket: str = "hour",
) -> dict[str, Any]:
    """Error rate for the window, plus a per-bucket series."""
    _validate_bucket(bucket)
    bucket_column = _bucket_column(bucket)

    errors = func.count().filter(_IS_ERROR).label("errors")

    statement = _in_window(
        select(bucket_column, func.count().label("total"), errors), start, end
    ).group_by(bucket_column).order_by(bucket_column)

    rows = (await session.execute(statement)).all()

    series = []
    total_count = 0
    total_errors = 0
    for row in rows:
        row_total = int(row.total)
        row_errors = int(row.errors)
        total_count += row_total
        total_errors += row_errors
        series.append(
            {
                "bucket": _isoformat(row.bucket),
                "total": row_total,
                "errors": row_errors,
                "error_rate": _ratio(row_errors, row_total),
            }
        )

    return {
        "total": total_count,
        "errors": total_errors,
        "error_rate": _ratio(total_errors, total_count),
        "series": series,
    }
