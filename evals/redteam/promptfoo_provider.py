"""promptfoo custom provider: sends one red-team case to the local Aporia API."""

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redteam.loaders import case_request, load_cases, load_problems  # noqa: E402
from redteam.run import parse_sse  # noqa: E402

API = os.environ.get("APORIA_EVAL_API", "http://localhost:8000")
CASES = {c["id"]: c for c in load_cases()}
PROBLEMS = load_problems()


def call_api(prompt, options, context):
    case = CASES[context["vars"]["case_id"]]
    body = case_request(case, PROBLEMS[case["problem_slug"]])
    device = f"promptfoo-{case['id']}-{os.getpid()}"
    headers = {"content-type": "application/json", "X-Aporia-Device": device}
    if options.get("config", {}).get("guard_off"):
        headers["X-Aporia-Disable-Guard"] = "1"
    req = urllib.request.Request(
        f"{API}/v1/hint", data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as res:
            events = parse_sse(res.read().decode())
    except Exception as exc:  # noqa: BLE001
        return {"error": f"API request failed: {exc}"}
    return {"output": "".join(d["text"] for n, d in events if n == "token")}
