from sqlalchemy import select

from app.models import Concept, ConceptMastery, ConceptNote, Mistake, Problem, ProblemSummary
from app.rag.constants import EMBED_DIM


async def test_rag_models_round_trip(db_session_factory) -> None:
    vec = [0.1] * EMBED_DIM
    async with db_session_factory() as s:
        s.add(Concept(slug="sliding-window", name="Sliding window", prerequisites=["two-pointers"]))
        s.add(Problem(slug="p", title="P", difficulty="Easy", tags=[], supported=True))
        await s.flush()
        s.add(
            ConceptNote(
                concept_slug="sliding-window",
                heading="Idea",
                body="b",
                content_hash="h",
                embedding=vec,
            )
        )
        s.add(ProblemSummary(slug="p", summary="x", concepts=["sliding-window"], embedding=vec))
        s.add(
            Mistake(
                device_hash="d",
                problem_slug="p",
                concept_slug="sliding-window",
                description="Fails on one element",
                embedding=vec,
            )
        )
        s.add(ConceptMastery(device_hash="d", concept_slug="sliding-window", p_known=0.2, n_obs=1))
        await s.commit()
    async with db_session_factory() as s:
        note = (await s.scalars(select(ConceptNote))).one()
        assert len(note.embedding or []) == EMBED_DIM
        mastery = (await s.scalars(select(ConceptMastery))).one()
        assert mastery.p_known == 0.2 and mastery.n_obs == 1
        summary = (await s.scalars(select(ProblemSummary))).one()
        assert summary.concepts == ["sliding-window"] and not summary.needs_review
