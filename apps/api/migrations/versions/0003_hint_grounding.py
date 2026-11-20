"""hints: grounded flag and failure kind

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hints", sa.Column("grounded", sa.Boolean, nullable=False, server_default=sa.false())
    )
    op.add_column("hints", sa.Column("failure_kind", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("hints", "failure_kind")
    op.drop_column("hints", "grounded")
