from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.retrieval.qdrant_store import QdrantHttpError, QdrantSemanticStore
from agentic_platform.retrieval.semantic_chunks import SemanticChunk
from agentic_platform.retrieval.semantic_store import SemanticVectorStore
from agentic_platform.security.policy import Capability, CapabilityGrant, local_principal


def database_grant(*capabilities: Capability) -> CapabilityGrant:
    allowed = capabilities or (Capability.DATABASE_READ, Capability.DATABASE_WRITE)
    return CapabilityGrant(frozenset(allowed), Path.cwd(), local_principal("tenant"))


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, path, payload))
        return {"status": "ok"}


class ExistingCollectionTransport(RecordingTransport):
    def __init__(self, vector_size: int) -> None:
        super().__init__()
        self.vector_size = vector_size

    def request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, path, payload))
        if method == "PUT" and path == "/collections/chunks":
            raise QdrantHttpError(409)
        return {
            "result": {"config": {"params": {"vectors": {"size": self.vector_size}}}}
        }


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
        transport, grant=database_grant(), collection_name="framework_chunks", vector_size=3
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


def test_qdrant_collection_initialization_accepts_existing_matching_collection() -> None:
    transport = ExistingCollectionTransport(vector_size=3)

    QdrantSemanticStore(
        transport, grant=database_grant(), collection_name="chunks", vector_size=3
    )

    assert transport.calls == [
        ("PUT", "/collections/chunks", {"vectors": {"size": 3, "distance": "Cosine"}}),
        ("GET", "/collections/chunks", {}),
    ]


def test_qdrant_collection_initialization_rejects_existing_wrong_dimension() -> None:
    with pytest.raises(ValueError, match="dimension"):
        QdrantSemanticStore(
            ExistingCollectionTransport(vector_size=4),
            grant=database_grant(), collection_name="chunks", vector_size=3,
        )


def test_qdrant_delete_source_is_scope_filtered_and_null_safe() -> None:
    transport = RecordingTransport()
    store = QdrantSemanticStore(transport, grant=database_grant(), collection_name="chunks", vector_size=2)

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


def test_qdrant_replaces_source_chunks_in_one_scope_filtered_batch() -> None:
    transport = RecordingTransport()
    store = QdrantSemanticStore(
        transport, grant=database_grant(), collection_name="chunks", vector_size=3
    )

    store.replace_source_chunks(scope(), ((chunk(), (0.1, 0.2, 0.3)),))

    method, path, body = transport.calls[-1]
    assert (method, path) == ("POST", "/collections/chunks/points/batch?wait=true")
    deletion, upsert = body["operations"]
    must = deletion["delete"]["filter"]["must"]
    matched = {entry["key"]: entry["match"]["value"] for entry in must if "match" in entry}
    assert matched == {
        "customer_id": "tenant", "framework_id": "framework",
        "framework_version_id": "2.0", "project_id": "project",
        "module_id": "api", "kind": "source",
    }
    assert upsert["upsert"]["points"][0]["payload"]["chunk_id"] == chunk().chunk_id


def test_qdrant_rejects_invalid_vectors_and_unsafe_configuration_before_write() -> None:
    transport = RecordingTransport()
    with pytest.raises(ValueError, match="collection_name"):
        QdrantSemanticStore(transport, grant=database_grant(), collection_name="other/name", vector_size=3)

    store = QdrantSemanticStore(transport, grant=database_grant(), collection_name="chunks", vector_size=3)
    calls_after_schema = len(transport.calls)
    with pytest.raises(ValueError, match="dimension"):
        store.upsert([(chunk(), (0.1, 0.2))])
    with pytest.raises(ValueError, match="finite"):
        store.upsert([(chunk(), (0.1, float("nan"), 0.3))])
    with pytest.raises(ValueError, match="source_path"):
        store.delete_source(scope(), "../secret")
    assert len(transport.calls) == calls_after_schema


def test_qdrant_requires_typed_database_authority_before_collection_initialization() -> None:
    transport = RecordingTransport()

    with pytest.raises(TypeError, match="grant"):
        QdrantSemanticStore(transport, collection_name="chunks", vector_size=3)
    with pytest.raises(TypeError, match="CapabilityGrant"):
        QdrantSemanticStore(
            transport, grant=None, collection_name="chunks", vector_size=3
        )  # type: ignore[arg-type]
    with pytest.raises(PermissionError, match="database_write"):
        QdrantSemanticStore(
            transport, grant=database_grant(Capability.DATABASE_READ),
            collection_name="chunks", vector_size=3,
        )

    assert transport.calls == []


def test_qdrant_checks_read_and_write_capabilities_before_transport_access() -> None:
    read_transport = RecordingTransport()
    read_only = QdrantSemanticStore(
        read_transport, grant=database_grant(Capability.DATABASE_READ),
        collection_name="chunks", vector_size=3, initialize_collection=False,
    )
    with pytest.raises(PermissionError, match="database_write"):
        read_only.upsert([(chunk(), (0.1, 0.2, 0.3))])
    with pytest.raises(PermissionError, match="database_write"):
        read_only.delete_source(scope(), "src/worker.py")
    assert read_transport.calls == []

    write_transport = RecordingTransport()
    write_only = QdrantSemanticStore(
        write_transport, grant=database_grant(Capability.DATABASE_WRITE),
        collection_name="chunks", vector_size=3, initialize_collection=False,
    )
    with pytest.raises(PermissionError, match="database_read"):
        write_only.search(scope(), (0.1, 0.2, 0.3), limit=1)
    assert write_transport.calls == []


def test_qdrant_url_factory_denies_invalid_or_read_only_grant_before_transport_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[str] = []

    def fail_transport(*args: object, **kwargs: object) -> object:
        constructed.append("called")
        raise AssertionError("transport must not be constructed")

    monkeypatch.setattr(
        "agentic_platform.retrieval.qdrant_store.QdrantHttpTransport", fail_transport
    )
    with pytest.raises(TypeError, match="CapabilityGrant"):
        QdrantSemanticStore.from_url(
            "https://qdrant.invalid", grant=None, collection_name="chunks", vector_size=3
        )  # type: ignore[arg-type]
    with pytest.raises(PermissionError, match="database_write"):
        QdrantSemanticStore.from_url(
            "https://qdrant.invalid",
            grant=database_grant(Capability.DATABASE_READ),
            collection_name="chunks", vector_size=3,
        )
    assert constructed == []


def test_qdrant_denies_cross_tenant_scope_before_transport_access() -> None:
    transport = RecordingTransport()
    store = QdrantSemanticStore(
        transport, grant=database_grant(), collection_name="chunks", vector_size=3
    )
    calls_after_schema = len(transport.calls)
    other_scope = KnowledgeScope("other", "framework", "2.0", "project", "api")
    other_chunk = SemanticChunk.create(
        scope=other_scope, source_path="src/worker.py", kind="source",
        content="pass\n", start_line=1, end_line=1,
        repository_revision="revision-7", language_id="python", symbol="worker",
    )

    with pytest.raises(PermissionError, match="tenant mismatch"):
        store.upsert([(other_chunk, (0.1, 0.2, 0.3))])
    with pytest.raises(PermissionError, match="tenant mismatch"):
        store.delete_source(other_scope, "src/worker.py")
    with pytest.raises(PermissionError, match="tenant mismatch"):
        store.search(other_scope, (0.1, 0.2, 0.3), limit=1)

    assert len(transport.calls) == calls_after_schema
