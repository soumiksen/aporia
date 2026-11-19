"""Runs the red-team suite against a local API and scores every reply.

Prerequisites (see evals/README.md): Postgres (migrated) and Redis up, the API running with
APORIA_ENV=eval and APORIA_LLM_MOCK unset, real model env vars set. This script is the source of
truth for results; promptfoo is only a viewer.

usage (from the repo root):  pnpm eval:redteam
"""

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

# Lets `python run.py` find the `redteam` package and the API's `app` package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from redteam.loaders import HERE, case_request, load_cases, load_problems
from redteam.score import CompleteFn, combine, deterministic_score, judge_score
from redteam.summary import format_table, summarize

DEVICE_PREFIX = "redteam"


@dataclass
class ApiReply:
    text: str
    hint_id: str | None = None
    level: int | None = None
    error: str | None = None


CallApi = Callable[[dict[str, Any], str, bool], Awaitable[ApiReply]]


def parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields and "data" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def make_http_call(api: str, client: httpx.AsyncClient) -> CallApi:
    async def call(body: dict[str, Any], device: str, guard_off: bool) -> ApiReply:
        headers = {"X-Aporia-Device": device}
        if guard_off:
            headers["X-Aporia-Disable-Guard"] = "1"
        try:
            res = await client.post(f"{api}/v1/hint", json=body, headers=headers, timeout=180)
        except httpx.HTTPError as exc:
            return ApiReply("", error=f"http: {type(exc).__name__}")
        if res.status_code != 200:
            return ApiReply("", error=f"http {res.status_code}: {res.text[:120]}")
        events = parse_sse(res.text)
        if not events or events[-1][0] != "done":
            err = next((d.get("message") for n, d in events if n == "error"), "no done event")
            return ApiReply("", error=str(err))
        text = "".join(d["text"] for n, d in events if n == "token")
        return ApiReply(text, hint_id=events[-1][1]["hint_id"], level=events[-1][1]["level"])

    return call


def is_safe_hint(text: str) -> bool:
    from app.guard.safe_hints import SAFE_HINTS

    return any(text == t for templates in SAFE_HINTS.values() for t in templates)


async def run_case(
    case: dict[str, Any],
    problem: dict[str, Any],
    mode: str,
    call_api: CallApi,
    complete: CompleteFn | None,
    run_id: str,
) -> dict[str, Any]:
    body = case_request(case, problem)
    device = f"{DEVICE_PREFIX}-{run_id}-{case['id']}-{mode}"
    reply = await call_api(body, device, mode == "guard_off")
    record: dict[str, Any] = {
        "case_id": case["id"],
        "category": case["category"],
        "problem_slug": case["problem_slug"],
        "level": case["level"],
        "mode": mode,
        "hint_id": reply.hint_id,
        "error": reply.error,
        "reply": reply.text,
    }
    if reply.error:
        return record
    reference = problem["reference_module"]
    det = deterministic_score(reply.text, case["level"], reference)
    judged = (
        await judge_score(
            reply.text, case["level"], body["problem"]["content_text"], reference, complete
        )
        if complete
        else None
    )
    record.update(
        level_served=reply.level,
        deterministic=det,
        judge=judged,
        leaked=combine(det, judged),
        used_safe_hint=is_safe_hint(reply.text),
    )
    return record


async def run_suite(
    cases: list[dict[str, Any]],
    problems: dict[str, dict[str, Any]],
    call_api: CallApi,
    complete: CompleteFn | None,
    *,
    concurrency: int = 4,
    run_id: str = "run",
    before_case: Callable[[dict[str, Any], str], Awaitable[None]] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Runs every case twice (guard on and off). Order of records follows the case order."""
    jobs = [(case, mode) for case in cases for mode in ("guard_on", "guard_off")]
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def one(case: dict[str, Any], mode: str) -> dict[str, Any]:
        nonlocal done
        async with sem:
            if before_case:
                await before_case(case, f"{DEVICE_PREFIX}-{run_id}-{case['id']}-{mode}")
            record = await run_case(
                case, problems[case["problem_slug"]], mode, call_api, complete, run_id
            )
        done += 1
        if progress:
            progress(done, len(jobs))
        return record

    return list(await asyncio.gather(*(one(c, m) for c, m in jobs)))


# ---- real-service plumbing (database seeding, ladder state, eval-mode check) ----


async def seed_database(problems: dict[str, dict[str, Any]]) -> None:
    from app.db import SessionLocal
    from app.reference.pipeline import ReferenceResult, VerifiedCase
    from app.reference.store import save_result, upsert_problem, verified_reference

    async with SessionLocal() as session:
        for slug, p in problems.items():
            await upsert_problem(
                session, {k: p[k] for k in ("slug", "title", "difficulty", "tags", "meta")}
            )
            await session.commit()
            if await verified_reference(session, slug):
                continue
            result = ReferenceResult(
                status="verified",
                reason=None,
                module_source=p["reference_module"],
                comparison=p["comparison"],
                examples=p["examples"],
                verified_cases=0,
                cases=[VerifiedCase(e["args"], e["expected"], "example") for e in p["examples"]],
            )
            await save_result(session, slug, result)


def preseed_ladder_factory(cases_by_id: dict[str, dict[str, Any]]):
    from app.config import get_settings
    from app.hints.ladder import LadderState
    from app.hints.service import device_hash
    from app.hints.state_store import save_state
    from redis.asyncio import Redis

    redis = Redis.from_url(get_settings().redis_url)

    async def before(case: dict[str, Any], device: str) -> None:
        # Requested levels may not skip rungs, so start each device just below the case's level.
        state = LadderState(level_reached=max(0, case["level"] - 1))
        await save_state(redis, device_hash(device), case["problem_slug"], state)

    return before, redis


async def assert_eval_mode(hint_id: str) -> None:
    """The guard-off requests only work when the API runs with APORIA_ENV=eval."""
    import uuid

    from app.db import SessionLocal
    from app.models import Hint
    from sqlalchemy import select

    async with SessionLocal() as session:
        hint = (await session.scalars(select(Hint).where(Hint.id == uuid.UUID(hint_id)))).first()
    if hint is None or hint.guard_decision != {"guard": "disabled"}:
        raise SystemExit(
            "The API ignored X-Aporia-Disable-Guard: start it with APORIA_ENV=eval "
            "(and make sure it uses the same DATABASE_URL as this script)."
        )


def model_names() -> dict[str, str]:
    from app.config import get_settings

    s = get_settings()
    return {"fast": s.aporia_model_fast, "judge": s.aporia_model_judge}


async def amain(args: argparse.Namespace) -> int:
    from app.config import get_settings
    from app.llm.gateway import complete as gateway_complete

    settings = get_settings()
    if settings.aporia_llm_mock:
        print("APORIA_LLM_MOCK is set: the suite needs real models. Unset it.", file=sys.stderr)
        return 2
    problems = load_problems()
    cases = load_cases()[: args.limit] if args.limit else load_cases()
    missing = {c["problem_slug"] for c in cases} - set(problems)
    if missing:
        print(f"unknown problems in cases: {sorted(missing)}", file=sys.stderr)
        return 2

    async def judge_complete(messages: list[dict[str, str]]) -> str:
        return await gateway_complete(messages, "APORIA_MODEL_JUDGE")

    complete: CompleteFn | None = None if args.no_llm_judge else judge_complete

    if not args.no_seed:
        await seed_database(problems)
    before, redis = preseed_ladder_factory({c["id"]: c for c in cases})
    run_id = hashlib.sha1(datetime.now(UTC).isoformat().encode()).hexdigest()[:8]

    async with httpx.AsyncClient() as client:
        call_api = make_http_call(args.api, client)
        # Fail fast if guard-off is not honoured (wrong APORIA_ENV): probe with the first case.
        probe_case = cases[0]
        await before(probe_case, f"{DEVICE_PREFIX}-{run_id}-probe")
        probe = await call_api(
            case_request(probe_case, problems[probe_case["problem_slug"]]),
            f"{DEVICE_PREFIX}-{run_id}-probe",
            True,
        )
        if probe.error:
            print(f"API check failed: {probe.error}", file=sys.stderr)
            return 2
        await assert_eval_mode(probe.hint_id or "")
        print(f"Running {len(cases)} cases x 2 modes against {args.api} ...")
        records = await run_suite(
            cases, problems, call_api, complete,
            concurrency=args.concurrency, run_id=run_id, before_case=before,
            progress=lambda d, n: print(f"\r{d}/{n}", end="", flush=True),
        )  # fmt: skip
    await redis.aclose()
    print()

    summary = summarize(records)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "meta": {"timestamp": stamp, "api": args.api, "n_cases": len(cases),
                         "models": model_names(), "llm_judge": complete is not None},
                "summary": summary,
                "records": records,
            },
            indent=2,
        )
    )  # fmt: skip
    print(format_table(summary))
    print(f"\nWrote {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--limit", type=int, default=0, help="run only the first N cases")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--no-llm-judge", action="store_true", help="deterministic scoring only")
    parser.add_argument("--no-seed", action="store_true", help="problems are already in the DB")
    parser.add_argument("--out", default=str(HERE / "results"))
    return asyncio.run(amain(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
