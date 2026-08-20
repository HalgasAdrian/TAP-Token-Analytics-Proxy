"""Asynchronous request-log persistence (A2).

The proxy hands each finished request here as a plain dict via a FastAPI
BackgroundTask, so persistence never sits on the response path.

Security invariant: `record` is assembled by `proxy._build_log_record`, which
never places the Authorization header or any key material into it. Nothing in
this module reads request headers.
"""

from __future__ import annotations

import logging

from app.db import AsyncSessionLocal
from app.models import RequestLog

logger = logging.getLogger(__name__)

# Columns a caller may supply. `id` and `created_at` are database-generated, and
# filtering to this set keeps an unexpected key in `record` from raising inside
# the ORM constructor.
_WRITABLE_COLUMNS: frozenset[str] = frozenset(
    column.name for column in RequestLog.__table__.columns
) - {"id", "created_at"}


async def write_request_log(record: dict) -> None:
    """Insert one `request_logs` row from `record`.

    Opens its own session rather than reusing the request-scoped one: this runs
    after the response has been sent, by which point FastAPI has already closed
    the session yielded by `get_session`.

    Never raises. A telemetry write is not worth failing on, and by the time
    this executes the client already holds its response.
    """
    fields = {key: value for key, value in record.items() if key in _WRITABLE_COLUMNS}

    try:
        async with AsyncSessionLocal() as session:
            session.add(RequestLog(**fields))
            await session.commit()
    except Exception:
        # exception() logs the traceback without interrupting the task.
        logger.exception("failed to persist request log")
