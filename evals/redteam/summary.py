from collections import defaultdict
from typing import Any

MODES = ("guard_off", "guard_on")


def _rate(leaks: int, n: int) -> float | None:
    return round(leaks / n, 4) if n else None


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Leak rates per mode and category. Errored requests are counted but not scored."""
    cats: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: {m: {"n": 0, "leaks": 0, "errors": 0, "safe_hints": 0} for m in MODES}
    )
    for r in records:
        bucket = cats[r["category"]][r["mode"]]
        if r.get("error"):
            bucket["errors"] += 1
            continue
        bucket["n"] += 1
        bucket["leaks"] += 1 if r["leaked"] else 0
        bucket["safe_hints"] += 1 if r.get("used_safe_hint") else 0

    overall = {m: {"n": 0, "leaks": 0, "errors": 0, "safe_hints": 0} for m in MODES}
    per_category: dict[str, Any] = {}
    for cat, modes in sorted(cats.items()):
        per_category[cat] = {}
        for m in MODES:
            b = modes[m]
            per_category[cat][m] = {**b, "leak_rate": _rate(b["leaks"], b["n"])}
            for k in b:
                overall[m][k] += b[k]
    return {
        "guard_off_leak_rate": _rate(overall["guard_off"]["leaks"], overall["guard_off"]["n"]),
        "guard_on_leak_rate": _rate(overall["guard_on"]["leaks"], overall["guard_on"]["n"]),
        "guard_on_safe_hint_rate": _rate(
            overall["guard_on"]["safe_hints"], overall["guard_on"]["n"]
        ),
        "overall": {
            m: {**overall[m], "leak_rate": _rate(overall[m]["leaks"], overall[m]["n"])}
            for m in MODES
        },
        "per_category": per_category,
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def format_table(summary: dict[str, Any]) -> str:
    rows = [("category", "off n", "off leak", "on n", "on leak", "on safe-hint")]
    for cat, modes in summary["per_category"].items():
        off, on = modes["guard_off"], modes["guard_on"]
        safe = _rate(on["safe_hints"], on["n"])
        rows.append(
            (
                cat,
                str(off["n"]),
                _pct(off["leak_rate"]),
                str(on["n"]),
                _pct(on["leak_rate"]),
                _pct(safe),
            )
        )
    o = summary["overall"]
    rows.append(
        (
            "ALL",
            str(o["guard_off"]["n"]),
            _pct(summary["guard_off_leak_rate"]),
            str(o["guard_on"]["n"]),
            _pct(summary["guard_on_leak_rate"]),
            _pct(summary["guard_on_safe_hint_rate"]),
        )
    )
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(c.ljust(widths[i]) for i, c in enumerate(r)) for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    lines.insert(-1, "  ".join("-" * w for w in widths))
    errors = o["guard_off"]["errors"] + o["guard_on"]["errors"]
    if errors:
        lines.append(f"\n{errors} request(s) errored and were not scored.")
    return "\n".join(lines)
