import pytest

from app.rag.taxonomy import TaxonomyError, load_taxonomy, parse_taxonomy


def doc(*items: dict) -> dict:
    return {"concepts": list(items)}


def test_real_taxonomy_loads() -> None:
    t = load_taxonomy()
    assert 38 <= len(t.slugs) <= 45
    assert "sliding-window" in t and "dp-2d" in t


def test_cycle_is_rejected() -> None:
    with pytest.raises(TaxonomyError, match="cycle"):
        parse_taxonomy(
            doc(
                {"slug": "a", "name": "A", "prerequisites": ["b"]},
                {"slug": "b", "name": "B", "prerequisites": ["a"]},
            )
        )


def test_missing_prerequisite_is_rejected() -> None:
    with pytest.raises(TaxonomyError, match="does not exist"):
        parse_taxonomy(doc({"slug": "a", "name": "A", "prerequisites": ["ghost"]}))


def test_duplicate_slug_and_shape_errors() -> None:
    with pytest.raises(TaxonomyError, match="duplicate"):
        parse_taxonomy(doc({"slug": "a", "name": "A"}, {"slug": "a", "name": "A2"}))
    with pytest.raises(TaxonomyError):
        parse_taxonomy({"nope": []})
    with pytest.raises(TaxonomyError):
        parse_taxonomy(doc({"slug": "a"}))


def test_self_prerequisite_is_a_cycle() -> None:
    with pytest.raises(TaxonomyError, match="cycle"):
        parse_taxonomy(doc({"slug": "a", "name": "A", "prerequisites": ["a"]}))
