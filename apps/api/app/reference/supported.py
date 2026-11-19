from typing import Any

# Problems that need these types or formats get supported = false and fall back to prompt-only
# hints (no execution). This is a deliberate Stage 2 scope limit.
UNSUPPORTED_TYPE_MARKERS = ("ListNode", "TreeNode", "Node")


def is_supported(meta: dict[str, Any] | None) -> tuple[bool, str | None]:
    """Returns (supported, reason). `meta` is LeetCode-style metaData (name, params, return)."""
    if not meta:
        return False, "no_meta"
    if meta.get("systemdesign") or "classname" in meta or "methods" in meta:
        return False, "design_class"
    if meta.get("manual"):
        return False, "manual_judge"
    name = meta.get("name")
    params = meta.get("params")
    if not isinstance(name, str) or not name or not isinstance(params, list):
        return False, "no_method"
    types: list[str] = []
    for param in params:
        if not isinstance(param, dict):
            return False, "bad_params"
        types.append(str(param.get("type", "")))
    ret = meta.get("return")
    return_type = str(ret.get("type", "")) if isinstance(ret, dict) else ""
    types.append(return_type)
    for t in types:
        if any(marker in t for marker in UNSUPPORTED_TYPE_MARKERS):
            return False, "linked_structure"
    if return_type in ("void", ""):
        return False, "void_or_unknown_return"
    return True, None
