import fakeredis

from app.llm.prompts import load_prompt, render
from app.ratelimit import hit, is_allowed, window_key


def test_prompt_sections_and_placeholders() -> None:
    system, user = load_prompt("hint_l1_v1")
    assert "Socratic" in system and "write code" in system
    assert "untrusted" in system
    for key in (
        "title",
        "difficulty",
        "tags",
        "content_text",
        "language",
        "code",
        "student_message",
    ):
        assert "{" + key + "}" in user


def test_render_is_safe_with_braces_and_missing_keys() -> None:
    out = render("A {title} B {code} C {unknown}", {"title": "T", "code": "x = {1}"})
    assert out == "A T B x = {1} C "


def test_window_key_and_limit() -> None:
    assert window_key("d", 0) == window_key("d", 59.9)
    assert window_key("d", 60) != window_key("d", 59.9)
    assert is_allowed(30, 30) and not is_allowed(31, 30)


async def test_hit_resets_each_window() -> None:
    r = fakeredis.FakeAsyncRedis()
    assert [await hit(r, "d", 2, now=0) for _ in range(3)] == [True, True, False]
    assert await hit(r, "d", 2, now=61) is True
