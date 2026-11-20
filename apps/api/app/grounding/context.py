"""What grounding reveals to the generator, and what only the guard may see.

The generator sees the minimal failing input, the student's actual output, the failure kind and a
one-line trace. The expected output and the reference code never reach the generator: they are
passed only to the guard (`GuardFacts`).
"""

import json
from dataclasses import dataclass
from typing import Any, Literal

from app.grounding.finder import Failure

MAX_FIELD_CHARS = 300

Status = Literal["failure_found", "no_failure"]


@dataclass(frozen=True)
class GroundingContext:
    status: Status
    failing_input: list[Any] | None = None
    actual_output: Any = None
    failure_kind: str | None = None
    trace_summary: str | None = None


@dataclass(frozen=True)
class GuardFacts:
    """For the guard only. Never rendered into a generator prompt."""

    failing_input: list[Any]
    expected_output: Any
    actual_output: Any
    failure_kind: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "input": self.failing_input,
            "expected": self.expected_output,
            "actual": self.actual_output,
            "kind": self.failure_kind,
        }


def build_context(failure: Failure | None) -> tuple[GroundingContext, GuardFacts | None]:
    if failure is None:
        return GroundingContext("no_failure"), None
    context = GroundingContext(
        status="failure_found",
        failing_input=failure.input,
        actual_output=failure.actual,
        failure_kind=failure.kind,
        trace_summary=failure.trace_summary,
    )
    facts = GuardFacts(failure.input, failure.expected, failure.actual, failure.kind)
    return context, facts


def _short(value: Any) -> str:
    text = json.dumps(value, separators=(", ", ": "), default=str)
    return text if len(text) <= MAX_FIELD_CHARS else text[: MAX_FIELD_CHARS - 3] + "..."


def render_for_prompt(context: GroundingContext | None, level: int) -> str:
    """Text for the {grounding} placeholder of the level prompts.

    Level 1 reveals nothing specific. From level 2 the minimal failing input and the student's
    actual output may be shown; the expected output and the fix never are.
    """
    if context is None or level < 2:
        return ""
    if context.status == "no_failure":
        return (
            "Grounding: the student's code was run against many inputs and no failing input was "
            "found. Do NOT claim or imply that the code is correct. Suggest that the student test "
            "other kinds of inputs (edge cases, larger inputs) themselves.\n"
        )
    lines = [
        "Grounding (verified by running the student's code):",
        f"- A minimal input on which the student's code fails: {_short(context.failing_input)}",
    ]
    if context.failure_kind == "runtime_error":
        lines.append(
            "- On that input the student's code raised an error"
            + (f": {context.trace_summary}" if context.trace_summary else ".")
        )
    elif context.failure_kind == "timeout":
        lines.append("- On a large input the student's code did not finish within the time limit.")
    else:
        lines.append(
            f"- On that input the student's code returned: {_short(context.actual_output)}"
        )
    lines.append(
        "Guide the student to trace their own code by hand on that input. Do NOT state what the "
        "correct or expected output is, and do NOT state the fix."
    )
    return "\n".join(lines) + "\n"
