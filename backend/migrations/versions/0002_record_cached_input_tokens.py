"""record cached input tokens

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-26 22:32:14.966591
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "request_logs", sa.Column("cached_input_tokens", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("request_logs", "cached_input_tokens")
