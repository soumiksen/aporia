import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.rag.constants import EMBED_DIM

# JSONB on Postgres; plain JSON elsewhere (the unit tests use in-memory SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")
# pgvector on Postgres; a JSON list elsewhere. The `tsv` full-text columns exist only in the
# migration (generated columns), so the models stay portable to the SQLite unit tests.
EmbeddingType = Vector(EMBED_DIM).with_variant(JSON(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Problem(Base):
    __tablename__ = "problems"

    slug: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    difficulty: Mapped[str] = mapped_column(String)
    tags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    supported: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReferenceSolution(Base):
    __tablename__ = "reference_solutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    problem_slug: Mapped[str] = mapped_column(ForeignKey("problems.slug"), index=True)
    module_source: Mapped[str] = mapped_column(Text)
    comparison: Mapped[str] = mapped_column(String, default="exact")  # exact | unordered
    status: Mapped[str] = mapped_column(String)  # verified | failed
    examples: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    verified_cases: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TestCase(Base):
    __test__ = False  # not a pytest class
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    problem_slug: Mapped[str] = mapped_column(ForeignKey("problems.slug"), index=True)
    args: Mapped[list[Any]] = mapped_column(JSONType)
    expected: Mapped[Any] = mapped_column(JSONType, nullable=True)
    source: Mapped[str] = mapped_column(String)  # example | generated


class Hint(Base):
    __tablename__ = "hints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    device_hash: Mapped[str] = mapped_column(String, index=True)
    problem_slug: Mapped[str] = mapped_column(String, index=True)
    level: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    guard_decision: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    rewrite_count: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # True when the hint cites a real minimal failing case found by running the student's code
    grounded: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_hash: Mapped[str] = mapped_column(String, index=True)
    problem_slug: Mapped[str] = mapped_column(String, index=True)
    code_hash: Mapped[str] = mapped_column(String)  # a hash only, never the student's code
    verdict: Mapped[str] = mapped_column(String)
    failing_case: Mapped[Any | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    """First-party telemetry (opt-in). Never contains code or problem text."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    device_hash: Mapped[str] = mapped_column(String, index=True)
    type: Mapped[str] = mapped_column(String, index=True)
    slug: Mapped[str | None] = mapped_column(String, nullable=True)
    props: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Concept(Base):
    __tablename__ = "concepts"

    slug: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    parent_slug: Mapped[str | None] = mapped_column(String, nullable=True)
    prerequisites: Mapped[list[str]] = mapped_column(JSONType, default=list)


class ConceptNote(Base):
    __tablename__ = "concept_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    concept_slug: Mapped[str] = mapped_column(ForeignKey("concepts.slug"), index=True)
    heading: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType, nullable=True)


class ProblemSummary(Base):
    """A short LLM-written summary and concept tags. Never the statement or examples."""

    __tablename__ = "problem_summaries"

    slug: Mapped[str] = mapped_column(ForeignKey("problems.slug"), primary_key=True)
    summary: Mapped[str] = mapped_column(Text)
    concepts: Mapped[list[str]] = mapped_column(JSONType, default=list)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType, nullable=True)


class Mistake(Base):
    """One sentence about a past failure, with an embedding. Never contains code."""

    __tablename__ = "mistakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_hash: Mapped[str] = mapped_column(String, index=True)
    problem_slug: Mapped[str] = mapped_column(String)
    concept_slug: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConceptMastery(Base):
    __tablename__ = "concept_mastery"

    device_hash: Mapped[str] = mapped_column(String, primary_key=True)
    concept_slug: Mapped[str] = mapped_column(String, primary_key=True)
    p_known: Mapped[float] = mapped_column(Float)
    n_obs: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
