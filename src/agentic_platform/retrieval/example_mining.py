"""Scope-safe representative example mining from semantic source matches."""
from __future__ import annotations

import math
from typing import Sequence

from agentic_platform.domain.models import CodeExample, KnowledgeScope
from agentic_platform.retrieval.semantic_chunks import ChunkKind
from agentic_platform.retrieval.semantic_store import SemanticMatch, SemanticVectorStore


class ExampleMiningError(ValueError):
    """A semantic candidate cannot safely become bounded coding context."""


def mine_representative_examples(
    store: SemanticVectorStore,
    scope: KnowledgeScope,
    query_vector: Sequence[float],
    *,
    limit: int = 6,
) -> tuple[CodeExample, ...]:
    """Return deterministic, deduplicated source examples for one scope.

    The three-times overfetch allows duplicate chunks for the same symbol to be
    collapsed while the public result remains tightly bounded.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer between 1 and 20")

    matches = store.search(
        scope, query_vector, limit=limit * 3, kind=ChunkKind.SOURCE
    )
    ranked: list[SemanticMatch] = []
    for match in matches:
        if not isinstance(match, SemanticMatch):
            raise ExampleMiningError("semantic result must be a typed match")
        chunk = match.chunk
        if chunk.scope != scope:
            raise ExampleMiningError("semantic example scope mismatch")
        if chunk.kind is not ChunkKind.SOURCE:
            raise ExampleMiningError("semantic example must be a source chunk")
        if chunk.symbol is None or not chunk.symbol.strip():
            raise ExampleMiningError("semantic source example requires a symbol")
        if (
            isinstance(match.score, bool)
            or not isinstance(match.score, (int, float))
            or not math.isfinite(match.score)
        ):
            raise ExampleMiningError("semantic example score must be finite")
        ranked.append(match)

    ranked.sort(
        key=lambda item: (
            -float(item.score),
            item.chunk.source_path,
            item.chunk.symbol or "",
            item.chunk.start_line,
            item.chunk.chunk_id,
        )
    )
    examples: list[CodeExample] = []
    seen: set[tuple[str, str]] = set()
    for match in ranked:
        chunk = match.chunk
        identity = (chunk.source_path, chunk.symbol or "")
        if identity in seen:
            continue
        seen.add(identity)
        score = float(match.score)
        examples.append(
            CodeExample(
                source_path=chunk.source_path,
                symbol=chunk.symbol or "",
                snippet=chunk.content,
                score=score,
                reasons=(f"semantic similarity: {score:.6f}",),
            )
        )
        if len(examples) == limit:
            break
    return tuple(examples)
