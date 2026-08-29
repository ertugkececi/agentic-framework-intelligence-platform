"""Provider-neutral persistence port for scoped semantic vectors."""
from __future__ import annotations

from typing import Protocol, Sequence

from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.retrieval.semantic_chunks import SemanticChunk


VectorEntry = tuple[SemanticChunk, Sequence[float]]


class SemanticVectorStore(Protocol):
    """Write boundary used by incremental semantic indexing."""

    def upsert(self, entries: Sequence[VectorEntry]) -> None: ...

    def delete_source(self, scope: KnowledgeScope, source_path: str) -> None: ...
