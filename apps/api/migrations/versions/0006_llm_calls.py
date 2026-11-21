"""llm_calls: one row per model call (purpose, tokens, cost, latency)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("purpose", sa.String, nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hint_id", sa.Uuid, nullable=True),
    )
    op.create_index("ix_llm_calls_ts", "llm_calls", ["ts"])
    op.create_index("ix_llm_calls_purpose", "llm_calls", ["purpose"])


def downgrade() -> None:
    op.drop_table("llm_calls")
