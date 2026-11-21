"""One-sentence, code-free description of a failure, from its kind and minimal failing input."""

from typing import Any

KIND_PHRASE = {
    "wrong_answer": "Returns a wrong answer",
    "runtime_error": "Crashes",
    "timeout": "Runs too slowly",
}
COUNT_WORDS = {1: "one", 2: "two", 3: "three"}


def _list_features(noun: str, items: list[Any]) -> list[str]:
    n = len(items)
    if n == 0:
        return [f"the {noun} is empty"]
    out: list[str] = []
    if n in COUNT_WORDS:
        word = COUNT_WORDS[n]
        out.append(f"the {noun} has {word} element{'s' if n > 1 else ''}")
    numbers = [x for x in items if isinstance(x, int | float) and not isinstance(x, bool)]
    hashable = [x for x in items if isinstance(x, str | int | float | bool)]
    if n > 1 and hashable and len(set(hashable)) == 1:
        out.append(f"all elements of the {noun} are equal")
    elif hashable and len(set(hashable)) < len(hashable):
        out.append(f"the {noun} has repeated values")
    if any(x < 0 for x in numbers):
        out.append(f"the {noun} has negative numbers")
    if any(x == 0 for x in numbers):
        out.append(f"the {noun} contains zero")
    return out


def _string_features(text: str) -> list[str]:
    if text == "":
        return ["the string is empty"]
    if len(text) == 1:
        return ["the string has a single character"]
    if len(set(text)) == 1:
        return ["the string repeats one character"]
    return []


def describe_failure(kind: str | None, failing_input: Any) -> str:
    """e.g. "Returns a wrong answer when the array has one element." Never contains code."""
    phrase = KIND_PHRASE.get(kind or "", "Fails")
    args = failing_input if isinstance(failing_input, list | tuple) else [failing_input]
    features: list[str] = []
    list_args = 0
    for arg in args:
        if isinstance(arg, list):
            list_args += 1
            noun = "array" if list_args == 1 else "second array"
            features += _list_features(noun, arg)
        elif isinstance(arg, str):
            features += _string_features(arg)
        elif isinstance(arg, int | float) and not isinstance(arg, bool):
            if arg == 0:
                features.append("a number is zero")
            elif arg < 0:
                features.append("a number is negative")
    features = features[:2]
    if not features:
        return f"{phrase} on a small input."
    return f"{phrase} when {' and '.join(features)}."
