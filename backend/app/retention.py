"""Ledger retention.

The ledger grows without bound otherwise, and stored bodies are the bulk of it.
Run `python -m app.cli prune-logs` on a schedule.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from app.db import AsyncSessionLocal
from app.models import RequestLog


def cutoff_for(retention_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=retention_days)


async def prune_request_logs(
    retention_days: int, *, dry_run: bool = False
) -> tuple[int, datetime]:
    """Delete rows older than `retention_days`; return the count and cutoff.

    Deleting by `created_at` uses its index, so this stays cheap as the table
    grows.
    """
    if retention_days <= 0:
        raise ValueError("retention_days must be positive to prune")

    cutoff = cutoff_for(retention_days)
    older_than_cutoff = RequestLog.created_at < cutoff

    async with AsyncSessionLocal() as session:
        if dry_run:
            matched = await session.scalar(
                select(func.count()).select_from(RequestLog).where(older_than_cutoff)
            )
            return int(matched or 0), cutoff

        result = await session.execute(delete(RequestLog).where(older_than_cutoff))
        await session.commit()
        return result.rowcount or 0, cutoff
