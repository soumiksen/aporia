"""concepts, notes, problem summaries, mistakes and concept mastery (RAG + learner model)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-20

The stage plan calls this `0004_rag_learner`; 0004 was already taken by `events`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.rag.constants import EMBED_DIM

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def tsv_column(expression: str) -> sa.Column:
    return sa.Column(
        "tsv",
        postgresql.TSVECTOR,
        sa.Computed(f"to_tsvector('english', {expression})", persisted=True),
    )


def upgrade() -> None:
    op.create_table(
        "concepts",
        sa.Column("slug", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("parent_slug", sa.String, nullable=True),
        sa.Column("prerequisites", JSONB, nullable=False, server_default="[]"),
    )
    op.create_table(
        "concept_notes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("concept_slug", sa.String, sa.ForeignKey("concepts.slug"), nullable=False),
        sa.Column("heading", sa.String, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String, nullable=False),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=True),
        tsv_column("heading || ' ' || body"),
    )
    op.create_table(
        "problem_summaries",
        sa.Column("slug", sa.String, sa.ForeignKey("problems.slug"), primary_key=True),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("concepts", JSONB, nullable=False, server_default="[]"),
        sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=True),
        tsv_column("summary"),
    )
    op.create_table(
        "mistakes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_hash", sa.String, nullable=False),
        sa.Column("problem_slug", sa.String, nullable=False),
        sa.Column("concept_slug", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=True),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "concept_mastery",
        sa.Column("device_hash", sa.String, nullable=False),
        sa.Column("concept_slug", sa.String, nullable=False),
        sa.Column("p_known", sa.Float, nullable=False),
        sa.Column("n_obs", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("device_hash", "concept_slug"),
    )
    op.create_index("ix_concept_notes_concept_slug", "concept_notes", ["concept_slug"])
    op.create_index("ix_mistakes_device_hash", "mistakes", ["device_hash"])
    for table in ("concept_notes", "problem_summaries"):
        op.create_index(f"ix_{table}_tsv", table, ["tsv"], postgresql_using="gin")
    for table in ("concept_notes", "problem_summaries", "mistakes"):
        op.create_index(
            f"ix_{table}_embedding",
            table,
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )


def downgrade() -> None:
    for table in ("concept_mastery", "mistakes", "problem_summaries", "concept_notes", "concepts"):
        op.drop_table(table)
