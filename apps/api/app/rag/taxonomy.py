"""Loads and validates the concept taxonomy (`knowledge/concepts.yaml`)."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

KNOWLEDGE_DIR = Path(__file__).resolve().parents[4] / "knowledge"
CONCEPTS_FILE = KNOWLEDGE_DIR / "concepts.yaml"


class TaxonomyError(ValueError):
    pass


@dataclass(frozen=True)
class ConceptDef:
    slug: str
    name: str
    aliases: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    parent_slug: str | None = None


@dataclass(frozen=True)
class Taxonomy:
    concepts: dict[str, ConceptDef] = field(default_factory=dict)

    @property
    def slugs(self) -> list[str]:
        return list(self.concepts)

    def __contains__(self, slug: object) -> bool:
        return slug in self.concepts


def parse_taxonomy(data: object) -> Taxonomy:
    if not isinstance(data, dict) or not isinstance(data.get("concepts"), list):
        raise TaxonomyError("concepts.yaml must have a top-level `concepts` list")
    concepts: dict[str, ConceptDef] = {}
    for raw in data["concepts"]:
        if not isinstance(raw, dict) or not raw.get("slug") or not raw.get("name"):
            raise TaxonomyError(f"every concept needs a slug and a name: {raw!r}")
        slug = str(raw["slug"])
        if slug in concepts:
            raise TaxonomyError(f"duplicate slug: {slug}")
        concepts[slug] = ConceptDef(
            slug=slug,
            name=str(raw["name"]),
            aliases=tuple(str(a) for a in raw.get("aliases") or []),
            prerequisites=tuple(str(p) for p in raw.get("prerequisites") or []),
            parent_slug=raw.get("parent"),
        )
    for c in concepts.values():
        for p in c.prerequisites:
            if p not in concepts:
                raise TaxonomyError(f"{c.slug}: prerequisite {p!r} does not exist")
        if c.parent_slug and c.parent_slug not in concepts:
            raise TaxonomyError(f"{c.slug}: parent {c.parent_slug!r} does not exist")
    _check_acyclic(concepts)
    return Taxonomy(concepts)


def _check_acyclic(concepts: dict[str, ConceptDef]) -> None:
    state: dict[str, int] = {}  # 1 = in progress, 2 = done

    def visit(slug: str, path: list[str]) -> None:
        if state.get(slug) == 2:
            return
        if state.get(slug) == 1:
            cycle = " -> ".join([*path[path.index(slug) :], slug])
            raise TaxonomyError(f"prerequisite cycle: {cycle}")
        state[slug] = 1
        for p in concepts[slug].prerequisites:
            visit(p, [*path, slug])
        state[slug] = 2

    for slug in concepts:
        visit(slug, [])


def load_taxonomy(path: Path = CONCEPTS_FILE) -> Taxonomy:
    return parse_taxonomy(yaml.safe_load(path.read_text(encoding="utf-8")))
