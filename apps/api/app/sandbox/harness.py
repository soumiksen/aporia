"""Harness that runs inside the sandbox, plus helpers to build programs and parse results.

The harness is a string template (it never runs in the API process). stdin is JSON:
  {"mode": "student" | "reference" | "reference_brute" | "validate", "method": str,
   "cases": [args, ...]}   ("validate" calls the module's validate(args) for each case)
  {"mode": "gen", "seed": int, "sizes": {"tiny": n, "small": n, "large": n}}
The last stdout line is a JSON list. Student/reference output per case: {ok, out, err, ms}.
gen output per generated case: {size, args, valid, err}.
"""

import json
from dataclasses import dataclass
from typing import Any

from app.sandbox.base import RunResult, SandboxError, SandboxRunner

HARNESS_TEMPLATE = r"""
import copy, io, json, random, signal, sys, time

SOURCE = __SOURCE__
PER_CASE_TIMEOUT = __TIMEOUT__
REAL_STDOUT = sys.stdout


def _alarm(signum, frame):
    raise TimeoutError("case timed out")


def _call(fn, args):
    sys.stdout = io.StringIO()
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, PER_CASE_TIMEOUT)
    started = time.perf_counter()
    try:
        out = fn(*copy.deepcopy(args))
        ok, err = True, None
    except BaseException as exc:
        out, ok, err = None, False, type(exc).__name__ + ": " + str(exc)[:200]
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        sys.stdout = REAL_STDOUT
    ms = round((time.perf_counter() - started) * 1000, 3)
    try:
        json.dumps(out)
    except (TypeError, ValueError):
        ok, out, err = False, None, "output is not JSON-serializable"
    return {"ok": ok, "out": out, "err": err, "ms": ms}


def _load():
    namespace = {"__name__": "aporia_sandbox_module"}
    exec(compile(SOURCE, "<source>", "exec"), namespace)
    return namespace


def _emit(results):
    sys.stdout = REAL_STDOUT
    sys.stdout.write("\n" + json.dumps(results) + "\n")
    sys.stdout.flush()


def main():
    request = json.loads(sys.stdin.read())
    mode = request["mode"]
    try:
        namespace = _load()
    except BaseException as exc:
        error = "load failed: " + type(exc).__name__ + ": " + str(exc)[:200]
        if mode == "gen":
            _emit([])
        else:
            _emit([{"ok": False, "out": None, "err": error, "ms": 0.0} for _ in request["cases"]])
        return

    if mode == "gen":
        results = []
        for size, count in request["sizes"].items():
            rng = random.Random("%s:%s" % (request["seed"], size))
            for _ in range(count):
                item = {"size": size, "args": None, "valid": False, "err": None}
                made = _call(lambda: namespace["gen"](rng, size), [])
                if not made["ok"]:
                    item["err"] = made["err"]
                else:
                    checked = _call(namespace["validate"], [made["out"]])
                    item["args"] = made["out"]
                    item["valid"] = bool(checked["ok"] and checked["out"] is True)
                    item["err"] = checked["err"]
                results.append(item)
        _emit(results)
        return

    if mode == "validate":
        validator = namespace["validate"]
        _emit([_call(lambda *a: validator(list(a)), args) for args in request["cases"]])
        return

    if mode == "student":
        try:
            fn = getattr(namespace["Solution"](), request["method"])
        except BaseException as exc:
            error = "no Solution." + str(request["method"]) + ": " + type(exc).__name__
            _emit([{"ok": False, "out": None, "err": error, "ms": 0.0} for _ in request["cases"]])
            return
    else:
        fn = namespace["solve_brute" if mode == "reference_brute" else "solve_optimal"]
    _emit([_call(fn, args) for args in request["cases"]])


main()
"""


@dataclass(frozen=True)
class CaseResult:
    ok: bool
    out: Any
    err: str | None
    ms: float


@dataclass(frozen=True)
class GenCase:
    size: str
    args: list[Any] | None
    valid: bool
    err: str | None


def build_program(source: str, per_case_timeout_s: float = 2.0) -> str:
    return HARNESS_TEMPLATE.replace("__SOURCE__", repr(source)).replace(
        "__TIMEOUT__", repr(float(per_case_timeout_s))
    )


def parse_last_json_line(stdout: str) -> Any | None:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line:
            try:
                return json.loads(line)
            except ValueError:
                return None
    return None


def _failed(n: int, reason: str) -> list[CaseResult]:
    return [CaseResult(False, None, f"sandbox: {reason}", 0.0) for _ in range(n)]


def _describe_failure(result: RunResult) -> str:
    if result.timed_out:
        return "time limit exceeded"
    tail = result.stderr.strip().splitlines()[-1:] or ["no output"]
    return f"run failed (exit {result.exit_code}): {tail[0][:200]}"


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def run_cases(
    runner: SandboxRunner,
    *,
    mode: str,
    source: str,
    method: str,
    cases: list[list[Any]],
    per_case_timeout_s: float = 2.0,
    batch_size: int = 50,
    time_limit_s: float = 10.0,
    memory_mb: int = 256,
) -> list[CaseResult]:
    """Runs cases in batches (many cases per submission). Returns one result per case, in order.

    A batch that times out or breaks yields failed results for that batch only. A broken sandbox
    raises SandboxError (the caller must fail safe).
    """
    program = build_program(source, per_case_timeout_s)
    results: list[CaseResult] = []
    for batch in _chunks(cases, batch_size):
        stdin = json.dumps({"mode": mode, "method": method, "cases": batch})
        run = await runner.run(program, stdin, time_limit_s, memory_mb)
        parsed = parse_last_json_line(run.stdout)
        if run.exit_code != 0 or run.timed_out or not isinstance(parsed, list):
            results.extend(_failed(len(batch), _describe_failure(run)))
            continue
        if len(parsed) != len(batch):
            results.extend(_failed(len(batch), "result count mismatch"))
            continue
        try:
            results.extend(
                CaseResult(bool(r["ok"]), r.get("out"), r.get("err"), float(r.get("ms", 0.0)))
                for r in parsed
            )
        except (TypeError, KeyError, AttributeError, ValueError) as exc:
            raise SandboxError(f"malformed harness output: {exc}") from exc
    return results


async def run_gen(
    runner: SandboxRunner,
    *,
    source: str,
    seed: int,
    sizes: dict[str, int],
    per_case_timeout_s: float = 2.0,
    time_limit_s: float = 20.0,
    memory_mb: int = 256,
) -> list[GenCase]:
    """Runs the module's gen and validate in the sandbox; returns generated cases with validity."""
    program = build_program(source, per_case_timeout_s)
    stdin = json.dumps({"mode": "gen", "seed": seed, "sizes": sizes})
    run = await runner.run(program, stdin, time_limit_s, memory_mb)
    parsed = parse_last_json_line(run.stdout)
    if run.exit_code != 0 or run.timed_out or not isinstance(parsed, list):
        raise SandboxError(f"gen failed: {_describe_failure(run)}")
    try:
        return [GenCase(str(r["size"]), r["args"], bool(r["valid"]), r.get("err")) for r in parsed]
    except (TypeError, KeyError) as exc:
        raise SandboxError(f"malformed gen output: {exc}") from exc
