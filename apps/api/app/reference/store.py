from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Problem, ReferenceSolution, TestCase
from app.reference.pipeline import ReferenceResult
from app.reference.supported import is_supported


async def upsert_problem(session: AsyncSession, problem: dict[str, Any]) -> Problem:
    """Stores slug, title, difficulty, tags, meta and the supported flag (never statement text)."""
    supported, _ = is_supported(problem.get("meta"))
    row = await session.get(Problem, problem["slug"])
    if row is None:
        row = Problem(
            slug=problem["slug"],
            title=problem.get("title", ""),
            difficulty=problem.get("difficulty", ""),
            tags=list(problem.get("tags", [])),
            meta=problem.get("meta"),
            supported=supported,
        )
        session.add(row)
    else:
        row.title = problem.get("title", row.title)
        row.difficulty = problem.get("difficulty", row.difficulty)
        row.tags = list(problem.get("tags", row.tags))
        row.meta = problem.get("meta", row.meta)
        row.supported = supported
    await session.flush()
    return row


async def latest_reference(session: AsyncSession, slug: str) -> ReferenceSolution | None:
    """Most recent reference row for the problem (any status), or None."""
    return (
        await session.scalars(
            select(ReferenceSolution)
            .where(ReferenceSolution.problem_slug == slug)
            .order_by(ReferenceSolution.id.desc())
            .limit(1)
        )
    ).first()


async def verified_reference(session: AsyncSession, slug: str) -> ReferenceSolution | None:
    return (
        await session.scalars(
            select(ReferenceSolution)
            .where(ReferenceSolution.problem_slug == slug, ReferenceSolution.status == "verified")
            .order_by(ReferenceSolution.id.desc())
            .limit(1)
        )
    ).first()


async def save_result(session: AsyncSession, slug: str, result: ReferenceResult) -> None:
    """Persists the reference row and, for verified references, the verified test cases."""
    session.add(
        ReferenceSolution(
            problem_slug=slug,
            module_source=result.module_source,
            comparison=result.comparison,
            status=result.status,
            examples=result.examples,
            verified_cases=result.verified_cases,
        )
    )
    if result.status == "verified":
        await session.execute(delete(TestCase).where(TestCase.problem_slug == slug))
        session.add_all(
            TestCase(problem_slug=slug, args=c.args, expected=c.expected, source=c.source)
            for c in result.cases
        )
    await session.commit()
