"""Optional cross-encoder rerank. Off by default; enable with APORIA_RERANK=1."""

import asyncio
import logging
from collections.abc import Sequence
from typing import Any, Protocol

from app.config import get_settings

logger = logging.getLogger("aporia.rag")

RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


class Reranker(Protocol):
    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """A relevance score per document (higher is better)."""
        ...


class NoopReranker:
    """Keeps the incoming order."""

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        return [float(len(documents) - i) for i in range(len(documents))]


class BgeReranker:
    """BAAI/bge-reranker-v2-m3 via sentence-transformers (uv group `rerank`). Loaded lazily."""

    def __init__(self, model_name: str = RERANK_MODEL) -> None:
        self.model_name = model_name
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder  # pyright: ignore[reportMissingImports]

            self._model = CrossEncoder(self.model_name)
        return self._model

    def _score(self, query: str, documents: Sequence[str]) -> list[float]:
        scores = self._load().predict([(query, d) for d in documents])
        return [float(s) for s in scores]

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        return await asyncio.to_thread(self._score, query, documents)


_bge: BgeReranker | None = None


def get_reranker() -> Reranker:
    """BgeReranker only when APORIA_RERANK=1; otherwise the no-op."""
    global _bge
    if not get_settings().aporia_rerank:
        return NoopReranker()
    if _bge is None:
        _bge = BgeReranker()
    return _bge
