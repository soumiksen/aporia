"""core tables: problems, reference_solutions, test_cases, hints, attempts

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "problems",
        sa.Column("slug", sa.String, primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("difficulty", sa.String, nullable=False),
        sa.Column("tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column("supported", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_table(
        "reference_solutions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("problem_slug", sa.String, sa.ForeignKey("problems.slug"), nullable=False),
        sa.Column("module_source", sa.Text, nullable=False),
        sa.Column("comparison", sa.String, nullable=False, server_default="exact"),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("examples", JSONB, nullable=False, server_default="[]"),
        sa.Column("verified_cases", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_reference_solutions_problem_slug", "reference_solutions", ["problem_slug"])
    op.create_table(
        "test_cases",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("problem_slug", sa.String, sa.ForeignKey("problems.slug"), nullable=False),
        sa.Column("args", JSONB, nullable=False),
        sa.Column("expected", JSONB, nullable=True),
        sa.Column("source", sa.String, nullable=False),
    )
    op.create_index("ix_test_cases_problem_slug", "test_cases", ["problem_slug"])
    op.create_table(
        "hints",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("device_hash", sa.String, nullable=False),
        sa.Column("problem_slug", sa.String, nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("guard_decision", JSONB, nullable=False, server_default="{}"),
        sa.Column("rewrite_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_hints_device_hash", "hints", ["device_hash"])
    op.create_index("ix_hints_problem_slug", "hints", ["problem_slug"])
    op.create_table(
        "attempts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_hash", sa.String, nullable=False),
        sa.Column("problem_slug", sa.String, nullable=False),
        sa.Column("code_hash", sa.String, nullable=False),
        sa.Column("verdict", sa.String, nullable=False),
        sa.Column("failing_case", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_attempts_device_hash", "attempts", ["device_hash"])
    op.create_index("ix_attempts_problem_slug", "attempts", ["problem_slug"])


def downgrade() -> None:
    for table in ("attempts", "hints", "test_cases", "reference_solutions", "problems"):
        op.drop_table(table)
