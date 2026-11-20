"""Concurrent batch execution: chunks of 50 cases, up to 4 chunks in flight, order preserved."""

import asyncio
from typing import Any

from app.sandbox.base import SandboxRunner
from app.sandbox.harness import CaseResult
from app.sandbox.harness import run_cases as run_chunk

CHUNK_SIZE = 50
MAX_CONCURRENT_CHUNKS = 4


async def run_cases(
    runner: SandboxRunner,
    source: str,
    mode: str,
    method: str,
    cases: list[list[Any]],
    per_case_timeout_s: float = 2.0,
    *,
    chunk_size: int = CHUNK_SIZE,
    concurrency: int = MAX_CONCURRENT_CHUNKS,
    time_limit_s: float = 10.0,
    memory_mb: int = 256,
) -> list[CaseResult]:
    """Runs `cases` in chunks concurrently and returns one result per case, in input order.

    A chunk that times out or breaks yields failed results for that chunk only (the harness
    reports it per case); a broken sandbox raises SandboxError for the whole call.
    """
    if not cases:
        return []
    chunks = [cases[i : i + chunk_size] for i in range(0, len(cases), chunk_size)]
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(chunk: list[list[Any]]) -> list[CaseResult]:
        async with semaphore:
            return await run_chunk(
                runner,
                mode=mode,
                source=source,
                method=method,
                cases=chunk,
                per_case_timeout_s=per_case_timeout_s,
                batch_size=len(chunk),
                time_limit_s=time_limit_s,
                memory_mb=memory_mb,
            )

    grouped = await asyncio.gather(*(one(c) for c in chunks))
    return [result for group in grouped for result in group]
