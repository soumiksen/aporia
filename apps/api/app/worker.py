import logging
from typing import Any

from arq.connections import RedisSettings

from app.config import get_settings
from app.db import SessionLocal
from app.llm.gateway import complete
from app.reference.pipeline import LLM, build_reference
from app.reference.store import save_result, upsert_problem
from app.sandbox.judge0 import Judge0Runner

logger = logging.getLogger("aporia.worker")


async def strong_llm(messages: list[dict[str, str]]) -> str:
    return await complete(messages, "APORIA_MODEL_STRONG")


async def build_reference_job(ctx: dict[str, Any], slug: str, problem: dict[str, Any]) -> str:
    """Builds and verifies the reference solution for a problem, then stores the outcome."""
    settings = get_settings()
    problem = {**problem, "slug": slug}
    session_factory = ctx.get("session_factory", SessionLocal)
    async with session_factory() as session:
        row = await upsert_problem(session, problem)
        await session.commit()
        if not row.supported:
            return "unsupported"
        if settings.aporia_llm_mock and "llm" not in ctx:
            return "skipped: mock mode has no real model"
        llm: LLM = ctx.get("llm", strong_llm)
        result = await build_reference(problem, llm=llm, runner=ctx["runner"])
        if result.infrastructure_error:
            logger.error("reference for %s not stored: %s", slug, result.reason)
            return f"infrastructure_error: {result.reason}"
        await save_result(session, slug, result)
        return result.status


async def on_startup(ctx: dict[str, Any]) -> None:
    ctx["runner"] = Judge0Runner(get_settings().judge0_url)


class WorkerSettings:
    functions = [build_reference_job]
    on_startup = on_startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = 900
    max_tries = 1
