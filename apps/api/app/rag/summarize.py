"""Problem concept summaries: the LLM's own words plus 1-3 taxonomy tags.

Only the summary, tags and embedding are stored. Never the statement, examples or code.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.llm.gateway import resolve_model
from app.llm.prompts import load_prompt, render
from app.models import ProblemSummary
from app.rag.embedder import Embedder
from app.rag.taxonomy import Taxonomy
from app.rag.text import shares_run
from app.reference.store import upsert_problem

logger = logging.getLogger("aporia.rag")

MAX_SUMMARY_WORDS = 90
COPY_RUN_WORDS = 8  # a verbatim run this long from the statement counts as copying
MAX_CONCEPTS = 3


class RawSummary(BaseModel):
    summary: str
    concepts: list[str]


# messages -> raw model output (validated here, so tests can mock it without a network)
SummaryLLM = Callable[[list[dict[str, str]]], Awaitable[RawSummary]]


@dataclass(frozen=True)
class SummaryResult:
    summary: str
    concepts: list[str]
    needs_review: bool


def copies_statement(summary: str, statement: str, run: int = COPY_RUN_WORDS) -> bool:
    """True if the summary repeats `run` or more consecutive words of the statement."""
    return shares_run(summary, statement, run)


def validate(raw: RawSummary, taxonomy: Taxonomy, statement: str) -> list[str]:
    """Reasons the output is unacceptable (empty list when fine)."""
    problems: list[str] = []
    unknown = [c for c in raw.concepts if c not in taxonomy]
    if unknown:
        problems.append(f"unknown concept slugs: {', '.join(unknown)}")
    if not 1 <= len(raw.concepts) <= MAX_CONCEPTS:
        problems.append(f"give 1 to {MAX_CONCEPTS} concepts, not {len(raw.concepts)}")
    if not raw.summary.strip() or len(raw.summary.split()) > MAX_SUMMARY_WORDS:
        problems.append(f"the summary must be 1 to {MAX_SUMMARY_WORDS} words")
    if "```" in raw.summary:
        problems.append("the summary must not contain code")
    if copies_statement(raw.summary, statement):
        problems.append("the summary copies phrases from the statement; use your own words")
    return problems


def build_messages(problem: dict[str, Any], taxonomy: Taxonomy, feedback: str = "") -> list[dict]:
    system, template = load_prompt("summarize_problem_v1")
    user = render(
        template,
        {
            "taxonomy": "\n".join(f"- {c.slug}: {c.name}" for c in taxonomy.concepts.values()),
            "title": problem.get("title", ""),
            "difficulty": problem.get("difficulty", ""),
            "tags": ", ".join(problem.get("tags", [])),
            "content_text": problem.get("content_text", ""),
            "feedback": feedback,
        },
    )
    # the allowed slugs live in the system prompt, where the model treats them as rules
    system = render(
        system, {"taxonomy": "\n".join(f"- {c.slug}" for c in taxonomy.concepts.values())}
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def generate_summary(
    problem: dict[str, Any], taxonomy: Taxonomy, llm: SummaryLLM
) -> SummaryResult:
    """Asks for a summary, validates it, retries once with feedback; after that the summary is
    stored with no concepts and marked `needs_review`."""
    statement = problem.get("content_text", "")
    feedback = ""
    last: RawSummary | None = None
    for _ in range(2):
        raw = await llm(build_messages(problem, taxonomy, feedback))
        problems = validate(raw, taxonomy, statement)
        if not problems:
            return SummaryResult(raw.summary.strip(), list(dict.fromkeys(raw.concepts)), False)
        last = raw
        feedback = "Your previous answer was rejected: " + "; ".join(problems) + ". Try again."
    # Never keep text that copies the statement; unknown slugs are dropped.
    keep_text = last is not None and not copies_statement(last.summary, statement)
    text = last.summary.strip() if last and keep_text else ""
    return SummaryResult(text, [], True)


async def instructor_summary(messages: list[dict[str, str]]) -> RawSummary:
    settings = get_settings()
    if settings.aporia_llm_mock:
        return RawSummary(summary="Mock summary of the reasoning involved.", concepts=[])
    model = resolve_model("APORIA_MODEL_FAST")
    import instructor

    from app.llm.calls import tracked
    from app.llm.router import get_router
    from app.llm.tracing import configure_tracing

    configure_tracing()
    client = instructor.from_litellm(get_router().acompletion)

    async def call() -> Any:
        return await client.chat.completions.create_with_completion(  # pyright: ignore[reportCallIssue,reportGeneralTypeIssues]
            model="fast",
            messages=messages,  # pyright: ignore[reportArgumentType]
            response_model=RawSummary,
            max_retries=0,
            metadata={"purpose": "problem_summary"},
        )

    parsed, _ = await tracked("problem_summary", model, call, response_of=lambda pair: pair[1])
    return parsed


def embed_text(result: SummaryResult, taxonomy: Taxonomy) -> str:
    names = " ".join(taxonomy.concepts[c].name for c in result.concepts if c in taxonomy)
    return f"{result.summary} {names}".strip()


async def summarize_and_store(
    factory: async_sessionmaker[AsyncSession],
    problem: dict[str, Any],
    taxonomy: Taxonomy,
    llm: SummaryLLM,
    embedder: Embedder,
) -> SummaryResult:
    result = await generate_summary(problem, taxonomy, llm)
    vector = (await embedder.embed([embed_text(result, taxonomy)]))[0] if result.summary else None
    async with factory() as session:
        await upsert_problem(session, problem)
        row = await session.get(ProblemSummary, problem["slug"])
        if row is None:
            row = ProblemSummary(slug=problem["slug"], summary="", concepts=[])
            session.add(row)
        row.summary, row.concepts = result.summary, result.concepts
        row.needs_review, row.embedding = result.needs_review, vector
        await session.commit()
    return result
