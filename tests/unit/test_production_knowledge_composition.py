from pathlib import Path

from agentic_platform.domain.models import CodingContext
from agentic_platform.orchestration.graph import DevelopmentService


def test_development_service_uses_injected_scoped_context_retriever(tmp_path: Path) -> None:
    calls = []

    def retrieve(repository, task):
        calls.append((repository, task.artifact_type, task.name))
        return [], CodingContext("BaseArtifact", "registered")

    service = DevelopmentService(context_retriever=retrieve)
    state = {
        "repository": str(tmp_path),
        "specification": type("Task", (), {
            "artifact_type": "service", "name": "InvoiceService", "operations": ()
        })(),
        "events": [],
    }

    result = service._retrieve(state)

    assert result["framework_rules"] == []
    assert isinstance(result["coding_context"], CodingContext)
    assert result["events"] == ["framework_retrieved"]
    assert calls == [(tmp_path, "service", "InvoiceService")]


def test_api_composes_scoped_postgres_and_qdrant_retrieval(monkeypatch) -> None:
    import importlib
    import sys

    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://platform@postgres/platform")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("TENANT_ID", "tenant-a")
    monkeypatch.setenv("QDRANT_COLLECTION", "framework-code")
    monkeypatch.setenv("EMBEDDING_VECTOR_SIZE", "3")
    sys.modules.pop("agentic_platform.api", None)
    api = importlib.import_module("agentic_platform.api")

    request = api.DevelopRequest(
        repository="repo", task="Create InvoiceService",
        customer_id="tenant-a", framework_id="framework",
        framework_version_id="4.0", project_id="billing",
        query_vector=[0.1, 0.2, 0.3],
    )
    captured = {}

    class RuleStore:
        def active_rules_for(self, prefix, *, scope=None):
            captured.setdefault("rule_scopes", []).append(scope)
            return []

        def close(self):
            captured["closed"] = True

    class SemanticStore:
        def search(self, scope, query_vector, *, limit, kind=None):
            captured["semantic"] = (scope, tuple(query_vector), limit, kind)
            return ()

    monkeypatch.setattr(api.PostgresKnowledgeStore, "from_dsn", lambda *a, **kw: RuleStore())
    monkeypatch.setattr(api.QdrantSemanticStore, "from_url", lambda *a, **kw: SemanticStore())

    def assemble(rule_store, semantic_store, scope, repository, task, query_vector):
        rule_store.active_rules_for("service", scope=scope)
        semantic_store.search(scope, query_vector, limit=1)
        return [], CodingContext("BaseArtifact", "registered")

    monkeypatch.setattr(api, "assemble_coding_context", assemble)

    retriever = api.production_context_retriever(request, Path("/workspace/repo"))
    rules, context = retriever(Path("/workspace/repo"), type("Task", (), {
        "artifact_type": "service", "name": "InvoiceService", "operations": ()
    })())

    assert rules == []
    assert isinstance(context, CodingContext)
    assert captured["rule_scopes"] == [request.knowledge_scope]
    assert captured["semantic"][0] == request.knowledge_scope
    assert captured["semantic"][1] == (0.1, 0.2, 0.3)
    assert captured["closed"] is True
