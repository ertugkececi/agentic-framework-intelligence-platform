from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.retrieval.qdrant_store import QdrantSemanticStore
from agentic_platform.retrieval.semantic_chunks import ChunkKind, SemanticChunk
from agentic_platform.retrieval.semantic_store import SemanticMatch, SemanticVectorStore
from agentic_platform.security.policy import Capability, CapabilityGrant


def database_grant(*capabilities: Capability) -> CapabilityGrant:
    allowed = capabilities or (Capability.DATABASE_READ, Capability.DATABASE_WRITE)
    return CapabilityGrant(frozenset(allowed), Path.cwd())


class SearchTransport:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {"result": []}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, path, payload))
        return self.response


def scope(module: str | None = "api") -> KnowledgeScope:
    return KnowledgeScope("tenant", "framework", "2.0", "project", module)


def payload(module: str | None = "api") -> dict[str, Any]:
    chunk = SemanticChunk.create(
        scope=scope(module), source_path="src/worker.py", kind="source",
        content="class Worker: pass", start_line=1, end_line=1,
        repository_revision="revision-7", language_id="python", symbol="Worker",
    )
    return {
        **chunk.filter_metadata,
        "chunk_id": chunk.chunk_id, "content_hash": chunk.content_hash,
        "content": chunk.content, "start_line": chunk.start_line,
        "end_line": chunk.end_line, "symbol": chunk.symbol,
    }



def test_search_uses_complete_scope_and_kind_filter_and_returns_typed_matches() -> None:
    transport = SearchTransport({"result": [{"score": 0.91, "payload": payload()}]})
    store: SemanticVectorStore = QdrantSemanticStore(
        transport, grant=database_grant(), collection_name="chunks", vector_size=3, initialize_collection=False
    )

    matches = store.search(scope(), (0.1, 0.2, 0.3), limit=4, kind=ChunkKind.SOURCE)

    assert matches == (SemanticMatch(chunk=matches[0].chunk, score=0.91),)
    assert matches[0].chunk.scope == scope()
    assert matches[0].chunk.kind is ChunkKind.SOURCE
    method, path, body = transport.calls[-1]
    assert (method, path) == ("POST", "/collections/chunks/points/search")
    assert body["vector"] == [0.1, 0.2, 0.3]
    assert body["limit"] == 4
    assert body["with_payload"] is True
    must = body["filter"]["must"]
    matched = {item["key"]: item["match"]["value"] for item in must if "match" in item}
    assert matched == {
        "customer_id": "tenant", "framework_id": "framework",
        "framework_version_id": "2.0", "project_id": "project",
        "module_id": "api", "kind": "source",
    }


def test_search_without_module_uses_null_filter_and_validates_inputs_before_request() -> None:
    transport = SearchTransport()
    store = QdrantSemanticStore(
        transport, grant=database_grant(), collection_name="chunks", vector_size=2, initialize_collection=False
    )
    assert store.search(scope(None), (0.2, 0.8), limit=1) == ()
    assert {"is_null": {"key": "module_id"}} in transport.calls[-1][2]["filter"]["must"]
    calls = len(transport.calls)
    with pytest.raises(ValueError, match="limit"):
        store.search(scope(), (0.2, 0.8), limit=0)
    with pytest.raises(ValueError, match="dimension"):
        store.search(scope(), (0.2,), limit=1)
    with pytest.raises(ValueError, match="finite"):
        store.search(scope(), (0.2, float("inf")), limit=1)
    assert len(transport.calls) == calls


def test_search_fails_closed_for_malformed_or_cross_scope_results() -> None:
    for response in (
        {"status": "ok"},
        {"result": [{"score": 1.0, "payload": {**payload(), "customer_id": "other"}}]},
        {"result": [{"score": "high", "payload": payload()}]},
        {"result": [{"score": 1.0, "payload": {**payload(), "content_hash": "0" * 64}}]},
    ):
        store = QdrantSemanticStore(
            SearchTransport(response), grant=database_grant(), collection_name="chunks", vector_size=2,
            initialize_collection=False,
        )
        with pytest.raises(RuntimeError, match="Qdrant search response"):
            store.search(scope(), (0.2, 0.8), limit=1)
