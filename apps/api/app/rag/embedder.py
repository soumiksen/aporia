"""Embeddings behind a small protocol: LiteLLM in production, a deterministic fake in tests."""

import asyncio
import hashlib
import json
import logging
import math
import re
from collections.abc import Sequence
from typing import Any, Protocol

from app.config import get_settings
from app.rag.constants import EMBED_DIM

logger = logging.getLogger("aporia.rag")

BATCH_SIZE = 64
CACHE_TTL_S = 30 * 24 * 3600
MAX_ATTEMPTS = 4


class EmbeddingError(RuntimeError):
    pass


class Embedder(Protocol):
    model: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def fit_dimension(vector: Sequence[float], dim: int = EMBED_DIM) -> list[float]:
    """Zero-pads a shorter vector to `dim` (cosine similarity is unchanged). Longer is an error."""
    if len(vector) > dim:
        raise EmbeddingError(
            f"embedding model returns {len(vector)} dimensions but EMBED_DIM is {dim}; "
            "pick a model with at most that many (or one that supports a `dimensions` option)"
        )
    return [*map(float, vector), *([0.0] * (dim - len(vector)))]


_WORD = re.compile(r"[a-z0-9]+")


class FakeEmbedder:
    """Deterministic hashed bag-of-words vectors of dimension EMBED_DIM. No network.

    Texts that share words get a higher cosine similarity, which is enough to test retrieval.
    """

    model = "fake-embedder"

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.dim = dim
        self.calls: list[list[str]] = []

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in _WORD.findall(text.lower()):
            digest = hashlib.sha256(word.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            vec[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            vec[0] = 1.0
            return vec
        return [v / norm for v in vec]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._one(t) for t in texts]


class LiteLLMEmbedder:
    """Embeds through LiteLLM in batches of 64, with retries and exponential backoff."""

    def __init__(self, model: str, *, sleep: Any = asyncio.sleep) -> None:
        if not model:
            raise EmbeddingError("APORIA_EMBEDDING_MODEL is not set")
        self.model = model
        self._sleep = sleep

    async def _batch(self, texts: list[str]) -> list[list[float]]:
        import litellm

        delay = 1.0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await litellm.aembedding(model=self.model, input=texts)
                rows = sorted(response.data, key=lambda r: r["index"])  # pyright: ignore[reportAttributeAccessIssue]
                return [fit_dimension(r["embedding"]) for r in rows]
            except EmbeddingError:
                raise
            except Exception as exc:  # noqa: BLE001
                if attempt == MAX_ATTEMPTS:
                    raise EmbeddingError(f"embedding failed: {type(exc).__name__}") from exc
                logger.warning("embedding attempt %d failed (%s)", attempt, type(exc).__name__)
                await self._sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        out: list[list[float]] = []
        for i in range(0, len(items), BATCH_SIZE):
            out.extend(await self._batch(items[i : i + BATCH_SIZE]))
        return out


class CachedEmbedder:
    """Wraps an embedder with a Redis cache keyed by sha256(model + text), 30-day TTL."""

    def __init__(self, inner: Embedder, redis: Any, ttl: int = CACHE_TTL_S) -> None:
        self.inner = inner
        self.model = inner.model
        self.redis = redis
        self.ttl = ttl

    def key(self, text: str) -> str:
        return "embed:" + hashlib.sha256((self.model + text).encode()).hexdigest()

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        results: list[list[float] | None] = [None] * len(items)
        missing: list[int] = []
        for i, text in enumerate(items):
            try:
                raw = await self.redis.get(self.key(text))
            except Exception:  # noqa: BLE001 - a cache outage must not break retrieval
                raw = None
            if raw is not None:
                results[i] = json.loads(raw)
            else:
                missing.append(i)
        if missing:
            fresh = await self.inner.embed([items[i] for i in missing])
            for i, vec in zip(missing, fresh, strict=True):
                results[i] = vec
                try:
                    await self.redis.set(self.key(items[i]), json.dumps(vec), ex=self.ttl)
                except Exception:  # noqa: BLE001
                    pass
        return [r for r in results if r is not None]


def get_embedder(redis: Any = None) -> Embedder | None:
    """The configured embedder, or None when RAG is not configured.

    Mock mode (APORIA_LLM_MOCK=1) uses the FakeEmbedder so dev works with no keys.
    """
    settings = get_settings()
    inner: Embedder
    if settings.aporia_llm_mock:
        inner = FakeEmbedder()
    elif settings.aporia_embedding_model:
        inner = LiteLLMEmbedder(settings.aporia_embedding_model)
    else:
        return None
    return CachedEmbedder(inner, redis) if redis is not None else inner
