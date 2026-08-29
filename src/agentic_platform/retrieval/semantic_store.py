"""Provider-neutral persistence port for scoped semantic vectors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.retrieval.semantic_chunks import ChunkKind, SemanticChunk


VectorEntry = tuple[SemanticChunk, Sequence[float]]


@dataclass(frozen=True)
class SemanticMatch:
    """A validated semantic chunk and its provider similarity score."""

    chunk: SemanticChunk
    score: float


class SemanticVectorStore(Protocol):
    """Read/write boundary used by scoped semantic indexing and retrieval."""

    def upsert(self, entries: Sequence[VectorEntry]) -> None: ...

    def delete_source(self, scope: KnowledgeScope, source_path: str) -> None: ...

    def search(
        self,
        scope: KnowledgeScope,
        query_vector: Sequence[float],
        *,
        limit: int,
        kind: ChunkKind | str | None = None,
    ) -> tuple[SemanticMatch, ...]: ...
