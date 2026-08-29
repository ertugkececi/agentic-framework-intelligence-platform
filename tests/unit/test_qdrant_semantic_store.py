from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.retrieval.qdrant_store import QdrantSemanticStore
from agentic_platform.retrieval.semantic_chunks import SemanticChunk
from agentic_platform.retrieval.semantic_store import SemanticVectorStore


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, path, payload))
        return {"status": "ok"}


def scope(module: str | None = "api") -> KnowledgeScope:
    return KnowledgeScope("tenant", "framework", "2.0", "project", module)


def chunk() -> SemanticChunk:
    return SemanticChunk.create(
        scope=scope(), source_path="src/worker.py", kind="source",
        content="class Worker:\n    pass\n", start_line=1, end_line=2,
        repository_revision="revision-7", language_id="python", symbol="Worker",
    )


def test_qdrant_adapter_satisfies_port_and_upserts_scoped_payload() -> None:
    transport = RecordingTransport()
    store: SemanticVectorStore = QdrantSemanticStore(
        transport, collection_name="framework_chunks", vector_size=3
    )

    item = chunk()
    store.upsert([(item, (0.1, 0.2, 0.3))])

    assert transport.calls[0] == (
        "PUT", "/collections/framework_chunks",
        {"vectors": {"size": 3, "distance": "Cosine"}},
    )
    method, path, body = transport.calls[1]
    assert (method, path) == ("PUT", "/collections/framework_chunks/points?wait=true")
    point = body["points"][0]
    UUID(point["id"])
    assert point["vector"] == [0.1, 0.2, 0.3]
    assert point["payload"]["chunk_id"] == item.chunk_id
    assert point["payload"]["customer_id"] == "tenant"
    assert point["payload"]["framework_version_id"] == "2.0"
    assert point["payload"]["content"] == item.content
    assert point["payload"]["start_line"] == 1


def test_qdrant_delete_source_is_scope_filtered_and_null_safe() -> None:
    transport = RecordingTransport()
    store = QdrantSemanticStore(transport, collection_name="chunks", vector_size=2)

    store.delete_source(scope(None), "docs/guide.md")

    method, path, body = transport.calls[-1]
    assert (method, path) == ("POST", "/collections/chunks/points/delete?wait=true")
    must = body["filter"]["must"]
    matched = {entry["key"]: entry["match"]["value"] for entry in must if "match" in entry}
    assert matched == {
        "customer_id": "tenant", "framework_id": "framework",
        "framework_version_id": "2.0", "project_id": "project",
        "source_path": "docs/guide.md",
    }
    assert {"is_null": {"key": "module_id"}} in must


def test_qdrant_rejects_invalid_vectors_and_unsafe_configuration_before_write() -> None:
    transport = RecordingTransport()
    with pytest.raises(ValueError, match="collection_name"):
        QdrantSemanticStore(transport, collection_name="other/name", vector_size=3)

    store = QdrantSemanticStore(transport, collection_name="chunks", vector_size=3)
    calls_after_schema = len(transport.calls)
    with pytest.raises(ValueError, match="dimension"):
        store.upsert([(chunk(), (0.1, 0.2))])
    with pytest.raises(ValueError, match="finite"):
        store.upsert([(chunk(), (0.1, float("nan"), 0.3))])
    with pytest.raises(ValueError, match="source_path"):
        store.delete_source(scope(), "../secret")
    assert len(transport.calls) == calls_after_schema
