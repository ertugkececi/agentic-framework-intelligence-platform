from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentic_platform.retrieval.embeddings import DeterministicEmbedding, EmbeddingProvider
from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.retrieval.source_indexing import (
    RepositorySemanticIndexer,
    RepositorySourceChunkExtractor,
)
from agentic_platform.security.policy import Capability, CapabilityGrant, local_principal


def _scope(project: str = "project-a") -> KnowledgeScope:
    return KnowledgeScope("tenant", "framework", "2.0", project)


def _grant(repository: Path, *capabilities: Capability) -> CapabilityGrant:
    return CapabilityGrant(frozenset(capabilities), repository, local_principal("tenant"))


def test_deterministic_embedding_satisfies_port_with_stable_finite_vectors() -> None:
    provider: EmbeddingProvider = DeterministicEmbedding(dimension=8)

    first = provider.embed(("class Worker: pass", "class Other: pass"))
    second = provider.embed(("class Worker: pass", "class Other: pass"))

    assert provider.dimension == 8
    assert first == second
    assert first[0] != first[1]
    assert all(len(vector) == 8 for vector in first)
    assert all(math.isfinite(value) for vector in first for value in vector)


@pytest.mark.parametrize("dimension", [0, -1, True, 4097])
def test_deterministic_embedding_rejects_unbounded_or_malformed_dimensions(dimension: object) -> None:
    with pytest.raises(ValueError, match="dimension"):
        DeterministicEmbedding(dimension=dimension)  # type: ignore[arg-type]


def test_source_extraction_uses_inventory_and_parser_provenance_without_raw_secrets(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "worker.py").write_text(
        "class Worker:\n    API_TOKEN = 'raw-secret-value'\n    pass\n",
        encoding="utf-8",
    )
    extractor = RepositorySourceChunkExtractor(
        grant=_grant(repository, Capability.READ_REPOSITORY)
    )

    chunks = extractor.extract(repository, _scope())

    assert len(chunks) == 1
    assert chunks[0].source_path == "worker.py"
    assert chunks[0].symbol == "Worker"
    assert (chunks[0].start_line, chunks[0].end_line) == (1, 3)
    assert chunks[0].language_id == "python"
    assert "raw-secret-value" not in chunks[0].content


def test_source_extraction_keeps_identical_files_isolated_by_mandatory_scope(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "worker.py").write_text("class Worker:\n    pass\n", encoding="utf-8")
    extractor = RepositorySourceChunkExtractor(
        grant=_grant(repository, Capability.READ_REPOSITORY)
    )

    first = extractor.extract(repository, _scope("project-a"))
    second = extractor.extract(repository, _scope("project-b"))

    assert first[0].chunk_id != second[0].chunk_id
    with pytest.raises(TypeError, match="KnowledgeScope"):
        extractor.extract(repository, None)  # type: ignore[arg-type]


class MemorySemanticStore:
    def __init__(self) -> None:
        self.entries: dict[str, object] = {}
        self.mutations = 0

    def replace_source_chunks(self, scope: KnowledgeScope, entries: object) -> None:
        self.mutations += 1
        self.entries = {
            key: value
            for key, value in self.entries.items()
            if getattr(value[0], "scope") != scope or getattr(value[0], "kind") != "source"
        }
        for entry in entries:  # type: ignore[union-attr]
            self.entries[entry[0].chunk_id] = entry


def test_indexing_replaces_changed_and_deleted_source_chunks_instead_of_appending(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "keep.py").write_text("class Keep:\n    pass\n", encoding="utf-8")
    (repository / "gone.py").write_text("class Gone:\n    pass\n", encoding="utf-8")
    grant = _grant(repository, Capability.READ_REPOSITORY, Capability.DATABASE_WRITE)
    store = MemorySemanticStore()
    indexer = RepositorySemanticIndexer(
        grant=grant,
        extractor=RepositorySourceChunkExtractor(grant=grant),
        embedding=DeterministicEmbedding(4),
        store=store,
    )

    assert indexer.index(repository, _scope()) == 2
    old_ids = set(store.entries)
    (repository / "keep.py").write_text("class Keep:\n    value = 2\n", encoding="utf-8")
    (repository / "gone.py").unlink()

    assert indexer.index(repository, _scope()) == 1
    assert len(store.entries) == 1
    assert not old_ids.intersection(store.entries)


class WrongDimensionEmbedding:
    dimension = 4

    def embed(self, texts: object) -> tuple[tuple[float, ...], ...]:
        return ((1.0,),)


def test_indexing_rejects_bad_provider_dimensions_before_store_mutation(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "worker.py").write_text("class Worker:\n    pass\n", encoding="utf-8")
    grant = _grant(repository, Capability.READ_REPOSITORY, Capability.DATABASE_WRITE)
    store = MemorySemanticStore()
    indexer = RepositorySemanticIndexer(
        grant=grant,
        extractor=RepositorySourceChunkExtractor(grant=grant),
        embedding=WrongDimensionEmbedding(),
        store=store,
    )

    with pytest.raises(ValueError, match="dimension"):
        indexer.index(repository, _scope())
    assert store.mutations == 0


def test_indexing_denies_missing_database_capability_before_store_mutation(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "worker.py").write_text("class Worker:\n    pass\n", encoding="utf-8")
    grant = _grant(repository, Capability.READ_REPOSITORY)
    store = MemorySemanticStore()
    indexer = RepositorySemanticIndexer(
        grant=grant,
        extractor=RepositorySourceChunkExtractor(grant=grant),
        embedding=DeterministicEmbedding(4),
        store=store,
    )

    with pytest.raises(PermissionError, match="database_write"):
        indexer.index(repository, _scope())
    assert store.mutations == 0


def test_production_learn_persists_structured_rules_and_semantic_chunks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import importlib
    import sys

    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://platform@postgres/platform")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("TENANT_ID", "tenant")
    monkeypatch.setenv("EMBEDDING_VECTOR_SIZE", "4")
    sys.modules.pop("agentic_platform.api", None)
    api = importlib.import_module("agentic_platform.api")
    repository = tmp_path / "repo"
    repository.mkdir()
    calls: dict[str, object] = {}

    class Learner:
        def learn(self, repo: Path) -> object:
            calls["learn"] = repo
            return SimpleNamespace(rules=["structured-rule"])

    class RuleStore:
        def replace_rules(self, rules: object, fingerprint: str, *, scope: KnowledgeScope) -> None:
            calls["rules"] = (rules, fingerprint, scope)

        def close(self) -> None:
            calls["closed"] = True

    class Indexer:
        def __init__(self, **dependencies: object) -> None:
            calls["dependencies"] = dependencies

        def index(self, repo: Path, scope: KnowledgeScope) -> int:
            calls["indexed"] = (repo, scope)
            return 1

    def qdrant_factory(*args: object, **kwargs: object) -> object:
        calls["qdrant"] = kwargs
        return object()

    monkeypatch.setattr(api, "FrameworkLearner", Learner)
    monkeypatch.setattr(api.PostgresKnowledgeStore, "from_dsn", lambda *a, **kw: RuleStore())
    monkeypatch.setattr(api.QdrantSemanticStore, "from_url", qdrant_factory)
    monkeypatch.setattr(api, "RepositorySemanticIndexer", Indexer)
    request = api.LearnRequest(
        repository="repo", framework_id="framework",
        framework_version_id="2.0", project_id="project-a",
    )

    rules = api.production_learn(request, repository)

    assert rules == ["structured-rule"]
    assert calls["rules"][2] == request.knowledge_scope  # type: ignore[index]
    assert calls["indexed"] == (repository, request.knowledge_scope)
    assert calls["qdrant"]["initialize_collection"] is True  # type: ignore[index]
    assert calls["closed"] is True
