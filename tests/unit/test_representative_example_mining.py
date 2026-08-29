from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import pytest

from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.retrieval.example_mining import ExampleMiningError, mine_representative_examples
from agentic_platform.retrieval.semantic_chunks import ChunkKind, SemanticChunk
from agentic_platform.retrieval.semantic_store import SemanticMatch, VectorEntry


def scope(customer: str = "tenant") -> KnowledgeScope:
    return KnowledgeScope(customer, "framework", "3.0", "project", "module")


def chunk(path: str, symbol: str | None, content: str, *, customer: str = "tenant") -> SemanticChunk:
    return SemanticChunk.create(
        scope=scope(customer),
        source_path=path,
        kind=ChunkKind.SOURCE,
        content=content,
        start_line=1,
        end_line=content.count("\n") + 1,
        repository_revision="revision-1",
        language_id="python",
        symbol=symbol,
    )


@dataclass
class RecordingStore:
    matches: tuple[SemanticMatch, ...]
    calls: list[tuple[KnowledgeScope, tuple[float, ...], int, ChunkKind | str | None]] = field(default_factory=list)

    def upsert(self, entries: Sequence[VectorEntry]) -> None:
        raise AssertionError("mining must not write")

    def delete_source(self, requested_scope: KnowledgeScope, source_path: str) -> None:
        raise AssertionError("mining must not delete")

    def search(self, requested_scope, query_vector, *, limit, kind=None):
        self.calls.append((requested_scope, tuple(query_vector), limit, kind))
        return self.matches


def test_mines_bounded_deduplicated_examples_in_deterministic_similarity_order() -> None:
    lower_duplicate = chunk("src/account.py", "AccountUnit", "class AccountUnit: pass")
    higher_duplicate = chunk("src/account.py", "AccountUnit", "class AccountUnit:\n    def load(self): pass")
    other = chunk("src/audit.py", "AuditUnit", "class AuditUnit: pass")
    store = RecordingStore((
        SemanticMatch(lower_duplicate, 0.72),
        SemanticMatch(other, 0.81),
        SemanticMatch(higher_duplicate, 0.93),
    ))

    examples = mine_representative_examples(store, scope(), (0.1, 0.2), limit=2)

    assert [(item.symbol, item.snippet, item.score) for item in examples] == [
        ("AccountUnit", higher_duplicate.content, 0.93),
        ("AuditUnit", other.content, 0.81),
    ]
    assert examples[0].reasons == ("semantic similarity: 0.930000",)
    assert store.calls == [(scope(), (0.1, 0.2), 6, ChunkKind.SOURCE)]


def test_mining_fails_closed_for_cross_scope_or_symbol_less_source_match() -> None:
    cross_scope = RecordingStore((SemanticMatch(chunk("src/unit.py", "Unit", "class Unit: pass", customer="other"), 0.9),))
    without_symbol = RecordingStore((SemanticMatch(chunk("src/module.py", None, "value = 1"), 0.8),))

    with pytest.raises(ExampleMiningError, match="scope"):
        mine_representative_examples(cross_scope, scope(), (0.1,), limit=1)
    with pytest.raises(ExampleMiningError, match="symbol"):
        mine_representative_examples(without_symbol, scope(), (0.1,), limit=1)


def test_mining_validates_bound_before_search() -> None:
    store = RecordingStore(())

    for invalid in (0, -1, True, 21):
        with pytest.raises(ValueError, match="limit"):
            mine_representative_examples(store, scope(), (0.1,), limit=invalid)
    assert store.calls == []
