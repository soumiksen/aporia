import json
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _normalize_unordered(value: Any) -> Any:
    """Sorts every list recursively (by canonical JSON) so element order never matters."""
    if isinstance(value, list):
        return sorted((_normalize_unordered(v) for v in value), key=_canonical)
    if isinstance(value, dict):
        return {k: _normalize_unordered(v) for k, v in value.items()}
    return value


def outputs_equal(a: Any, b: Any, mode: str) -> bool:
    """`exact` compares canonical JSON; `unordered` compares sorted JSON."""
    if mode == "unordered":
        return _canonical(_normalize_unordered(a)) == _canonical(_normalize_unordered(b))
    return _canonical(a) == _canonical(b)
