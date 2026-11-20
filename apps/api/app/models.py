import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB on Postgres; plain JSON elsewhere (the unit tests use in-memory SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")


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
