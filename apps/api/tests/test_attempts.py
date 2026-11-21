from sqlalchemy import select

from app.models import ConceptMastery, Problem, ProblemSummary

H = {"X-Aporia-Device": "dev-1"}


async def seed(factory) -> None:
    async with factory() as s:
        s.add(Problem(slug="p1", title="p", difficulty="Easy", tags=[], supported=False))
        await s.flush()
        s.add(ProblemSummary(slug="p1", summary="s", concepts=["sliding-window"]))
        await s.commit()


async def test_attempt_updates_mastery(client, db_session_factory) -> None:
    await seed(db_session_factory)
    r = await client.post("/v1/attempts", json={"slug": "p1", "verdict": "Accepted"}, headers=H)
    assert r.status_code == 204
    async with db_session_factory() as s:
        row = (await s.scalars(select(ConceptMastery))).one()
    assert row.concept_slug == "sliding-window" and row.n_obs == 1 and row.p_known > 0.2
    assert len(row.device_hash) == 64  # hashed device id


async def test_attempt_rejects_code_and_extra_fields(client) -> None:
    body = {"slug": "p1", "verdict": "Accepted", "code": "print(1)"}
    assert (await client.post("/v1/attempts", json=body, headers=H)).status_code == 422
    assert (
        await client.post("/v1/attempts", json={"slug": "P 1", "verdict": "x"}, headers=H)
    ).status_code == 422
    assert (
        await client.post("/v1/attempts", json={"slug": "p1", "verdict": "x"})
    ).status_code == 400


async def test_unknown_problem_is_a_no_op(client, db_session_factory) -> None:
    r = await client.post("/v1/attempts", json={"slug": "nope", "verdict": "Accepted"}, headers=H)
    assert r.status_code == 204
    async with db_session_factory() as s:
        assert (await s.scalars(select(ConceptMastery))).all() == []
