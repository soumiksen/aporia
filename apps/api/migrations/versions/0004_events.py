"""events table for opt-in first-party telemetry

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("device_hash", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("slug", sa.String, nullable=True),
        sa.Column(
            "props", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_events_device_hash", "events", ["device_hash"])
    op.create_index("ix_events_type", "events", ["type"])
    op.create_index("ix_events_ts", "events", ["ts"])


def downgrade() -> None:
    op.drop_table("events")
