# Execution-grounded hints

Aporia does not guess where a student's code is wrong. When it can, it runs the code against a
verified reference solution, finds a failing input, shrinks it to the smallest one that still
fails, and builds the hint around that input. The expected output never reaches the model that
writes the hint; only the leak guard sees it.

## When it applies
- The problem is `supported` (Python-friendly signature, no `ListNode`/`TreeNode`/design class),
- it has a `verified` reference (Stage 2), and the student's language is Python.
Otherwise hints stay prompt-only, exactly as before.

## Pipeline

```
student code ──► finder ──► shrinker ──► context ──► generator ──► guard ──► student
                  │            │            │            ▲           ▲
                  └─ reference ┴─ sandbox   │            │           │
                                            └─ input +   └─ never    └─ also sees the expected
                                               actual       sees        output and the reference
                                               output       expected
```

1. **Finder** (`app/grounding/finder.py`). Candidate inputs: the statement examples, stored test
   cases, 100 fresh `tiny`/`small` cases from the reference generator (fixed seed), then, only if
   nothing failed, 20 `large` cases for timeouts. The reference (`solve_optimal`) and the student
   run on the same inputs inside the sandbox; outputs are compared with the problem's comparison
   mode. Failure kinds: `wrong_answer`, `runtime_error`, `timeout` (2 s per case). Wrong answers and
   crashes on small inputs rank first, timeouts last. `trace_summary` is the last line of the
   exception, never a full traceback.
2. **Shrinker** (`app/grounding/shrink.py`). Generic delta debugging over the JSON arguments:
   remove halves, quarters, ... single elements; integers move toward 0 with geometrically
   shrinking steps; strings lose chunks and are simplified toward `a`; nested lists and dicts
   recurse. A candidate counts only if it fails *in the same way* and the reference module's own
   `validate(args)` accepts it (that check also runs in the sandbox). Budget: 150 evaluations or
   15 s, whichever comes first, and the smallest failing input found so far is kept.
3. **Context** (`app/grounding/context.py`). The generator gets the minimal input, the student's
   actual output (or the one-line error), and the failure kind. The expected output and the
   reference code go only to the guard (`GuardFacts`).
4. **Generation.** Level 1 reveals nothing from this. Levels 2 to 4 (`hint_l*_v2`) may mention the
   input and the student's output and ask the student to trace their own code on it by hand; they
   may never state the expected output or the fix. If no failing input was found the prompt says
   so and forbids claiming the code is correct.
5. **Guard.** The Stage 2 checks, plus a deterministic expected-output check (a cue phrase such as
   "should return" or "the answer is" followed by the expected value, or a long structured value
   outside the input quote) and a judge that is told about the failing case. A leak is rewritten
   once, then replaced by a safe hint.

The whole grounding step has a 12 s budget. On a timeout, a sandbox error or any other error the
hint continues prompt-only (still guarded) and the `done` event says `grounded: false`.

## Worked example (synthetic problem)

Problem "Pair Count": count index pairs `i < j` with `nums[i] + nums[j] == target`.

Student code (a plausible bug: `break` stops after the first partner of each element):
```python
class Solution:
    def pairCount(self, nums, target):
        count = 0
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                if nums[i] + nums[j] == target:
                    count += 1
                    break
        return count
```
- The finder runs the examples and a few hundred generated inputs. A typical first failure is a
  length-12 list of small numbers.
- The shrinker removes elements and moves values toward 0. Two elements can never expose this bug
  (an element has at most one partner), so it stops at three: `[[0, 0, 0], 0]`.
- The reference returns 3 for that input; the student's code returns 2.
- Level 2 prompt section (the generator sees this):
  ```
  Grounding (verified by running the student's code):
  - A minimal input on which the student's code fails: [[0, 0, 0], 0]
  - On that input the student's code returned: 2
  Guide the student to trace their own code by hand on that input. Do NOT state what the correct
  or expected output is, and do NOT state the fix.
  ```
- A good reply: "Try tracing your code by hand on nums = [0, 0, 0] with target 0. How many times does
  each element get paired, and what happens after your `break`?"
- A reply such as "On that input the correct answer is 3" is blocked by the guard
  (`reveals_expected_output`), rewritten once, and otherwise replaced by a safe hint.

This exact case is a test: `tests/test_grounded_hint.py::test_pipeline_returns_the_minimal_failing_input_for_the_buggy_solution`.

## What is stored
- `hints.grounded` and `hints.failure_kind` (migration 0003).
- One `attempts` row per hint request: a SHA-256 of the code (never the code), the verdict, and
  `{"kind", "input"}` of the failing case. The input comes from the reference generator or the
  statement examples, not from the student.

## Measured (synthetic set, offline)
`uv --directory apps/api run python ../../evals/grounding/measure.py`: 10 of 10 synthetic problems
grounded with a wrong student attempt each; minimal inputs of 3 to 15 JSON characters; median 0.18 s
and maximum 0.55 s with a local subprocess runner. Judge0 adds per-submission network latency, so
real latency will be higher; the 12 s budget caps it.
