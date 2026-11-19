"""Regression gate: exits non-zero if the guard-on leak rate exceeds the accepted baseline.

usage: python gate.py [results.json]    (defaults to the newest file in results/)
"""

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EPSILON = 1e-9


def latest_results(directory: Path = HERE / "results") -> Path | None:
    files = sorted(directory.glob("*.json"))
    return files[-1] if files else None


def evaluate_gate(results: dict[str, Any], baseline: dict[str, Any]) -> tuple[bool, str]:
    rate = results.get("summary", {}).get("guard_on_leak_rate")
    allowed = baseline["guard_on_leak_rate"]
    if rate is None:
        return False, "no scored guard-on replies: the run produced no usable data"
    if rate > allowed + EPSILON:
        return False, f"guard-on leak rate {rate:.4f} exceeds baseline {allowed:.4f}"
    return True, f"guard-on leak rate {rate:.4f} is within baseline {allowed:.4f}"


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else latest_results()
    if path is None or not path.exists():
        print("gate: no results file found (run the red-team suite first)", file=sys.stderr)
        return 2
    baseline = json.loads((HERE / "baseline.json").read_text())
    ok, message = evaluate_gate(json.loads(path.read_text()), baseline)
    print(f"gate: {'PASS' if ok else 'FAIL'}: {message} ({path.name})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
