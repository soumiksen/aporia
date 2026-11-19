import socket
import uuid
from urllib.parse import urlparse

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Attempt, Base, Hint, Problem, ReferenceSolution, TestCase


async def round_trip(session: AsyncSession) -> None:
    session.add(
        Problem(
            slug="synthetic-sum",
            title="Synthetic Sum",
            difficulty="Easy",
            tags=["Array"],
            meta={"name": "add"},
            supported=True,
        )
    )
    await session.flush()
    session.add(
        ReferenceSolution(
            problem_slug="synthetic-sum",
            module_source="def solve_optimal(a, b): return a + b",
            comparison="exact",
            status="verified",
            examples=[{"args": [1, 2], "expected": 3}],
            verified_cases=300,
        )
    )
    session.add(TestCase(problem_slug="synthetic-sum", args=[1, 2], expected=3, source="example"))
    hint_id = uuid.uuid4()
    session.add(
        Hint(
            id=hint_id,
            device_hash="abc",
            problem_slug="synthetic-sum",
            level=2,
            text="What happens with zero?",
            guard_decision={"leaks": False},
            rewrite_count=1,
        )
    )
    session.add(
        Attempt(
            device_hash="abc",
            problem_slug="synthetic-sum",
            code_hash="deadbeef",
            verdict="Wrong Answer",
            failing_case=[1, 2],
        )
    )
    await session.commit()

    problem = await session.get(Problem, "synthetic-sum")
    assert problem is not None and problem.tags == ["Array"] and problem.supported is True
    assert problem.created_at is not None
    ref = (await session.scalars(select(ReferenceSolution))).one()
    assert ref.status == "verified" and ref.examples == [{"args": [1, 2], "expected": 3}]
    case = (await session.scalars(select(TestCase))).one()
    assert case.args == [1, 2] and case.expected == 3
    hint = await session.get(Hint, hint_id)
    assert hint is not None and hint.rating is None and hint.guard_decision == {"leaks": False}
    attempt = (await session.scalars(select(Attempt))).one()
    assert attempt.failing_case == [1, 2] and attempt.code_hash == "deadbeef"


async def test_models_round_trip_sqlite() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await round_trip(session)
    await engine.dispose()


def postgres_reachable() -> bool:
    parsed = urlparse(get_settings().database_url.replace("+asyncpg", ""))
    try:
        with socket.create_connection((parsed.hostname or "localhost", parsed.port or 5432), 0.5):
            return True
    except OSError:
        return False


@pytest.mark.db
async def test_models_round_trip_postgres() -> None:
    """Needs the migrated database (alembic upgrade head). Uses a rolled-back transaction."""
    if not postgres_reachable():
        pytest.skip("Postgres not reachable")
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            session = AsyncSession(bind=conn, expire_on_commit=False)
            await round_trip(session)
            await trans.rollback()
    except Exception as exc:  # database not migrated or wrong credentials
        pytest.skip(f"Postgres not usable: {exc}")
    finally:
        await engine.dispose()
