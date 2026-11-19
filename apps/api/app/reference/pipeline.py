import ast
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.llm.prompts import load_prompt, render
from app.reference.compare import outputs_equal
from app.reference.supported import is_supported
from app.sandbox.base import SandboxError, SandboxRunner
from app.sandbox.harness import CaseResult, run_cases, run_gen

logger = logging.getLogger("aporia.reference")

LLM = Callable[[list[dict[str, str]]], Awaitable[str]]

REQUIRED_FUNCTIONS = ("solve_optimal", "solve_brute", "gen", "validate")
GEN_SIZES = {"tiny": 200, "small": 150, "large": 50}  # requested; invalid ones are filtered out
MIN_VERIFIED_CASES = 300
MAX_REPAIR_ROUNDS = 2
ANALYZE_RETRIES = 2
GEN_SEED = 20260101
REPORT_LIMIT = 1500  # characters of failure report fed back to the model


class Example(BaseModel):
    args: list[Any]
    expected: Any


class Analysis(BaseModel):
    examples: list[Example] = Field(min_length=1)
    method: str
    params: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    comparison: Literal["exact", "unordered"] = "exact"


@dataclass(frozen=True)
class VerifiedCase:
    args: list[Any]
    expected: Any
    source: Literal["example", "generated"]


@dataclass
class ReferenceResult:
    status: Literal["verified", "failed"]
    reason: str | None
    module_source: str = ""
    comparison: str = "exact"
    examples: list[dict[str, Any]] = field(default_factory=list)
    verified_cases: int = 0
    cases: list[VerifiedCase] = field(default_factory=list)
    repair_rounds: int = 0
    # True when the failure came from infrastructure (LLM or sandbox down), not from verification.
    # Such results must not be stored as a permanent "failed".
    infrastructure_error: bool = False


@dataclass
class Verification:
    ok: bool
    report: str = ""
    cases: list[VerifiedCase] = field(default_factory=list)


def extract_json(text: str) -> Any:
    """Parses a JSON object from a reply, tolerating code fences and surrounding prose."""
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(stripped)
    except ValueError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


def extract_python(text: str) -> str:
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip() + "\n"


def static_check(source: str) -> str | None:
    """Returns an error message, or None if the module parses and has the four functions."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"SyntaxError: {exc.msg} (line {exc.lineno})"
    defined = {n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    missing = [name for name in REQUIRED_FUNCTIONS if name not in defined]
    return f"missing top-level functions: {', '.join(missing)}" if missing else None


def _short(value: Any, limit: int = 160) -> str:
    text = json.dumps(value, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _problem_values(problem: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": problem.get("title", ""),
        "difficulty": problem.get("difficulty", ""),
        "tags": ", ".join(problem.get("tags", [])),
        "content_text": problem.get("content_text", ""),
        "meta": json.dumps(problem.get("meta")),
    }


async def analyze(problem: dict[str, Any], llm: LLM) -> Analysis | None:
    system, template = load_prompt("analyze_problem_v1")
    feedback = ""
    for _ in range(1 + ANALYZE_RETRIES):
        user = render(template, {**_problem_values(problem), "feedback": feedback})
        reply = await llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
        try:
            return Analysis.model_validate(extract_json(reply))
        except (ValueError, ValidationError) as exc:
            feedback = (
                f"Your previous reply was invalid ({str(exc)[:300]}). Reply with valid JSON only."
            )
    return None


async def write_module(problem: dict[str, Any], analysis: Analysis, llm: LLM) -> str:
    system, template = load_prompt("write_reference_v1")
    user = render(template, {**_problem_values(problem), "analysis": analysis.model_dump_json()})
    return extract_python(
        await llm([{"role": "system", "content": system}, {"role": "user", "content": user}])
    )


async def fix_module(
    problem: dict[str, Any], analysis: Analysis, source: str, report: str, llm: LLM
) -> str:
    system, template = load_prompt("fix_reference_v1")
    user = render(
        template,
        {
            **_problem_values(problem),
            "analysis": analysis.model_dump_json(),
            "module_source": source,
            "report": report[:REPORT_LIMIT],
        },
    )
    return extract_python(
        await llm([{"role": "system", "content": system}, {"role": "user", "content": user}])
    )


def _is_timeout(result: CaseResult) -> bool:
    return not result.ok and "timed out" in (result.err or "")


async def verify_module(
    source: str, analysis: Analysis, runner: SandboxRunner, seed: int = GEN_SEED
) -> Verification:
    """Examples must pass, and optimal and brute must agree on >= MIN_VERIFIED_CASES valid cases."""
    problem_error = static_check(source)
    if problem_error:
        return Verification(False, f"Static check failed: {problem_error}")

    mode = analysis.comparison

    # 1. statement examples through solve_optimal
    example_results = await run_cases(
        runner,
        mode="reference",
        source=source,
        method="",
        cases=[e.args for e in analysis.examples],
    )
    bad: list[str] = []
    for i, (example, got) in enumerate(zip(analysis.examples, example_results, strict=True)):
        if not got.ok:
            bad.append(f"example {i} args={_short(example.args)}: error {got.err}")
        elif not outputs_equal(got.out, example.expected, mode):
            bad.append(
                f"example {i} args={_short(example.args)}: expected {_short(example.expected)}, "
                f"solve_optimal returned {_short(got.out)}"
            )
    if bad:
        return Verification(False, "solve_optimal fails statement examples:\n" + "\n".join(bad[:5]))

    # 2. generated cases (gen and validate also run in the sandbox)
    generated = await run_gen(runner, source=source, seed=seed, sizes=GEN_SIZES)
    valid = [g for g in generated if g.valid and g.args is not None]
    if len(valid) < MIN_VERIFIED_CASES:
        errors = sorted({g.err for g in generated if g.err})[:3]
        return Verification(
            False,
            f"gen/validate produced only {len(valid)} valid cases out of {len(generated)} "
            f"requested (need at least {MIN_VERIFIED_CASES}). Errors: {errors}",
        )

    # 3. optimal vs brute on the valid cases
    case_args = [g.args for g in valid if g.args is not None]
    optimal = await run_cases(runner, mode="reference", source=source, method="", cases=case_args)
    brute = await run_cases(
        runner, mode="reference_brute", source=source, method="", cases=case_args
    )
    agreed: list[VerifiedCase] = []
    problems: list[str] = []
    for gen_case, opt, bru in zip(valid, optimal, brute, strict=True):
        args = gen_case.args or []
        if not opt.ok:
            problems.append(f"solve_optimal error on args={_short(args)}: {opt.err}")
        elif _is_timeout(bru) and gen_case.size == "large":
            continue  # brute force is allowed to be too slow on large cases; skip them
        elif not bru.ok:
            problems.append(f"solve_brute error on args={_short(args)}: {bru.err}")
        elif not outputs_equal(opt.out, bru.out, mode):
            problems.append(
                f"disagreement on args={_short(args)}: solve_optimal={_short(opt.out)} "
                f"solve_brute={_short(bru.out)}"
            )
        else:
            agreed.append(VerifiedCase(args, opt.out, "generated"))
    if problems:
        head = f"{len(problems)} of {len(valid)} generated cases failed. First ones:\n"
        return Verification(False, head + "\n".join(problems[:5]))
    if len(agreed) < MIN_VERIFIED_CASES:
        return Verification(
            False,
            f"only {len(agreed)} cases agreed (need {MIN_VERIFIED_CASES}); brute force timed out "
            "on too many cases. Make gen smaller or solve_brute faster.",
        )

    cases = [VerifiedCase(e.args, e.expected, "example") for e in analysis.examples] + agreed
    return Verification(True, cases=cases)


async def build_reference(
    problem: dict[str, Any], *, llm: LLM, runner: SandboxRunner, seed: int = GEN_SEED
) -> ReferenceResult:
    """Builds and verifies a reference solution. Never raises: failures become a result."""
    supported, why = is_supported(problem.get("meta"))
    if not supported:
        return ReferenceResult("failed", f"unsupported:{why}")

    try:
        analysis = await analyze(problem, llm)
        if analysis is None:
            return ReferenceResult("failed", "analysis_invalid")
        examples = [e.model_dump() for e in analysis.examples]

        source = await write_module(problem, analysis, llm)
        rounds = 0
        report = ""
        while True:
            verification = await verify_module(source, analysis, runner, seed)
            if verification.ok:
                return ReferenceResult(
                    status="verified",
                    reason=None,
                    module_source=source,
                    comparison=analysis.comparison,
                    examples=examples,
                    verified_cases=sum(1 for c in verification.cases if c.source == "generated"),
                    cases=verification.cases,
                    repair_rounds=rounds,
                )
            report = verification.report
            if rounds >= MAX_REPAIR_ROUNDS:
                return ReferenceResult(
                    status="failed",
                    reason=f"verification_failed: {report[:300]}",
                    module_source=source,
                    comparison=analysis.comparison,
                    examples=examples,
                    repair_rounds=rounds,
                )
            rounds += 1
            logger.info("reference repair round %d for %s", rounds, problem.get("slug"))
            source = await fix_module(problem, analysis, source, report, llm)
    except SandboxError as exc:
        logger.error("reference build: sandbox error: %s", exc)
        return ReferenceResult("failed", f"sandbox_error: {exc}", infrastructure_error=True)
    except Exception as exc:  # noqa: BLE001 - LLM or parsing outage must not crash the worker
        logger.error("reference build failed: %s", type(exc).__name__)
        return ReferenceResult(
            "failed", f"llm_error: {type(exc).__name__}", infrastructure_error=True
        )
