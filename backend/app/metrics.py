"""Metrics API — aggregates request_logs into dashboard-ready JSON.

Every metric is a query over the ledger; nothing is stored pre-aggregated, so
the numbers cannot drift from the rows they summarise.

The ledger records forwarded traffic only. Requests rejected at the auth or
rate-limit gate short-circuit before logging, so "error rate" means errors among
admitted requests.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import require_metrics_access
from app.db import get_session
from app.models import RequestLog

router = APIRouter(prefix="/metrics", dependencies=[Depends(require_metrics_access)])

_ALLOWED_BUCKETS: frozenset[str] = frozenset({"minute", "hour", "day", "week", "month"})

# Any non-2xx/3xx response, or a request that never reached the upstream.
_IS_ERROR = (RequestLog.status_code >= 400) | (RequestLog.error.is_not(None))


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
    """Constrain a statement to the half-open interval [start, end)."""
    if start is not None:
        statement = statement.where(RequestLog.created_at >= start)
    if end is not None:
        statement = statement.where(RequestLog.created_at < end)
    return statement


def _bucket_column(bucket: str):
    return func.date_trunc(bucket, RequestLog.created_at).label("bucket")


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


@router.get("/volume")
async def get_volume(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    bucket: str = Query(default="hour"),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Request volume over time."""
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
    """Latency percentiles over time."""
    return await query_latency_percentiles(session, start=start, end=end, bucket=bucket)


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


async def query_volume(
    session: AsyncSession,
    start: datetime | None = None,
    end: datetime | None = None,
    bucket: str = "hour",
) -> list[dict[str, Any]]:
    _validate_bucket(bucket)
    bucket_column = _bucket_column(bucket)

    statement = (
        _in_window(select(bucket_column, func.count().label("count")), start, end)
        .group_by(bucket_column)
        .order_by(bucket_column)
    )

    rows = (await session.execute(statement)).all()
    return [{"bucket": _isoformat(row.bucket), "count": int(row.count)} for row in rows]


async def query_cost_by_model(
    session: AsyncSession,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, Any]]:
    """Spend and token totals per model, most expensive first.

    Sums are coalesced because token columns are NULL for calls that reported no
    usage; without it, a model whose every call failed would return NULL.
    """
    model = func.coalesce(RequestLog.model, "unknown").label("model")
    cost = func.coalesce(func.sum(RequestLog.cost_usd), 0.0).label("cost_usd")

    statement = (
        _in_window(
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
        )
        .group_by(model)
        .order_by(cost.desc())
    )

    rows = (await session.execute(statement)).all()
    return [
        {
            "model": row.model,
            "requests": int(row.requests),
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
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
    """Median and p95 latency per bucket, interpolated with percentile_cont."""
    _validate_bucket(bucket)
    bucket_column = _bucket_column(bucket)

    statement = (
        _in_window(
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
        )
        .group_by(bucket_column)
        .order_by(bucket_column)
    )

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
    """Window hit rate plus its per-bucket series, folded from the same rows."""
    _validate_bucket(bucket)
    bucket_column = _bucket_column(bucket)
    hits = func.count().filter(RequestLog.cache_hit.is_(True)).label("hits")

    statement = (
        _in_window(select(bucket_column, func.count().label("total"), hits), start, end)
        .group_by(bucket_column)
        .order_by(bucket_column)
    )

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
    """Window error rate plus its per-bucket series."""
    _validate_bucket(bucket)
    bucket_column = _bucket_column(bucket)
    errors = func.count().filter(_IS_ERROR).label("errors")

    statement = (
        _in_window(
            select(bucket_column, func.count().label("total"), errors), start, end
        )
        .group_by(bucket_column)
        .order_by(bucket_column)
    )

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
