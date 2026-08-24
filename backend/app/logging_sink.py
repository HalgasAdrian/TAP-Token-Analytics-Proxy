"""Asynchronous request-log persistence."""

from __future__ import annotations

import json
import logging

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import RequestLog

logger = logging.getLogger(__name__)

_WRITABLE_COLUMNS: frozenset[str] = frozenset(
    column.name for column in RequestLog.__table__.columns
) - {"id", "created_at"}

_BODY_COLUMNS = ("request_body", "response_body")


def _cap_body(body: object, limit: int) -> object:
    """Replace an oversized body with a marker recording its real size.

    Bodies take up most of the space in request_logs, and one large prompt or
    completion can be megabytes. The marker keeps the row, and so keeps the
    metrics built from it, while dropping the payload.
    """
    if limit <= 0 or body is None:
        return body

    encoded_length = len(json.dumps(body, default=str))
    if encoded_length <= limit:
        return body
    return {"_truncated": True, "bytes": encoded_length}


async def write_request_log(record: dict) -> None:
    """Insert one request_logs row.

    Runs after the response has been sent, so it opens its own session rather
    than reusing the request-scoped one. Never raises: a failed telemetry write
    must not surface to a client that already holds its response.
    """
    fields = {key: value for key, value in record.items() if key in _WRITABLE_COLUMNS}

    for column in _BODY_COLUMNS:
        if column in fields:
            fields[column] = _cap_body(fields[column], settings.max_body_bytes)

    try:
        async with AsyncSessionLocal() as session:
            session.add(RequestLog(**fields))
            await session.commit()
    except Exception:
        logger.exception("failed to persist request log")
