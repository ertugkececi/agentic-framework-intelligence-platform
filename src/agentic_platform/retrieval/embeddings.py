"""Provider-neutral embedding boundary and deterministic local adapter."""
from __future__ import annotations

import hashlib
import math
from typing import Protocol, Sequence


MAX_EMBEDDING_DIMENSION = 4096


class EmbeddingProvider(Protocol):
    """Convert text into fixed-dimension finite vectors."""

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


class DeterministicEmbedding:
    """Dependency-free deterministic embedding for local/demo deployments."""

    def __init__(self, dimension: int = 384) -> None:
        if (
            not isinstance(dimension, int)
            or isinstance(dimension, bool)
            or not 1 <= dimension <= MAX_EMBEDDING_DIMENSION
        ):
            raise ValueError(f"dimension must be an integer from 1 to {MAX_EMBEDDING_DIMENSION}")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            if not isinstance(text, str):
                raise TypeError("embedding texts must be strings")
            values = []
            for index in range(self._dimension):
                digest = hashlib.sha256(
                    index.to_bytes(4, "big") + text.encode("utf-8")
                ).digest()
                values.append((int.from_bytes(digest[:8], "big") / (2**63)) - 1.0)
            norm = math.sqrt(sum(value * value for value in values)) or 1.0
            vectors.append(tuple(value / norm for value in values))
        return tuple(vectors)
