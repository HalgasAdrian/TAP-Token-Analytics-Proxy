"""The migrations must fully describe the models.

The schema under test is built by `alembic upgrade head` (see conftest), so this
compares that result against the ORM metadata. A non-empty diff means someone
changed a model without generating a migration — the failure that would
otherwise surface as a production insert error.
"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.db import Base, engine


async def test_models_and_migrations_have_not_drifted():
    async with engine.connect() as connection:
        diff = await connection.run_sync(
            lambda sync_connection: compare_metadata(
                MigrationContext.configure(sync_connection), Base.metadata
            )
        )

    assert diff == [], (
        "models and migrations have drifted; run "
        "`alembic revision --autogenerate` and review the result"
    )


async def test_metrics_queries_have_an_index_to_use():
    """created_at carries every metrics filter and the retention delete."""
    async with engine.connect() as connection:
        indexes = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_indexes("request_logs")
        )

    indexed_columns = {tuple(index["column_names"]) for index in indexes}
    assert ("created_at",) in indexed_columns
    assert ("project_id",) in indexed_columns
