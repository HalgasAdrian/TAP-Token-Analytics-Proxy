import logging

logger = logging.getLogger(__name__)


async def write_request_log(record: dict) -> None:
    logger.warning("ASSIGNMENT A2 write_request_log is not implemented; request logging is a no-op")
    # ============================================================
    # ASSIGNMENT: A2 persist request log
    # ------------------------------------------------------------
    # Implement: insert one RequestLog row from `record` using an AsyncSession
    #            (open a session inside this task; do not reuse a request session).
    # Why:       persists per-request telemetry that every /metrics endpoint aggregates.
    # Done when: with LOGGING_ENABLED=true each proxied call adds one request_logs row
    #            and no Authorization/key material is ever stored.
    # Reference: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
    #            https://fastapi.tiangolo.com/tutorial/background-tasks/
    # ============================================================
    raise NotImplementedError("ASSIGNMENT: A2 persist request log")
