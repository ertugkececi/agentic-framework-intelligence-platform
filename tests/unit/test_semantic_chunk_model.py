from dataclasses import FrozenInstanceError

import pytest

from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.retrieval.semantic_chunks import ChunkKind, SemanticChunk


def scope(customer: str = "tenant-a") -> KnowledgeScope:
    return KnowledgeScope(customer, "framework", "2.0", "project", "module")


def test_source_chunk_has_content_addressed_stable_identity() -> None:
    first = SemanticChunk.create(
        scope=scope(), source_path="src/package/worker.py", kind=ChunkKind.SOURCE,
        content="class Worker:\n    pass\n", start_line=4, end_line=5,
        repository_revision="revision-7", language_id="python", symbol="Worker",
    )
    second = SemanticChunk.create(
        scope=scope(), source_path="src/package/worker.py", kind="source",
        content="class Worker:\n    pass\n", start_line=4, end_line=5,
        repository_revision="revision-7", language_id="python", symbol="Worker",
    )
    assert first == second
    assert first.chunk_id == second.chunk_id
    assert len(first.chunk_id) == 64
    assert len(first.content_hash) == 64
    assert first.filter_metadata == {
        "customer_id": "tenant-a", "framework_id": "framework",
        "framework_version_id": "2.0", "project_id": "project", "module_id": "module",
        "kind": "source", "source_path": "src/package/worker.py",
        "language_id": "python", "repository_revision": "revision-7",
    }
    with pytest.raises(FrozenInstanceError):
        first.symbol = "Changed"  # type: ignore[misc]


def test_document_chunk_is_supported_without_language_or_symbol() -> None:
    chunk = SemanticChunk.create(
        scope=scope(), source_path="docs/guide.md", kind=ChunkKind.DOCUMENT,
        content="# Usage\n", start_line=1, end_line=1, repository_revision="revision-7",
    )
    assert chunk.kind is ChunkKind.DOCUMENT
    assert chunk.language_id is None
    assert chunk.symbol is None


def test_chunk_identity_is_isolated_by_scope_and_location() -> None:
    values = {
        SemanticChunk.create(
            scope=scope(customer), source_path="docs/guide.md", kind="document",
            content="same text", start_line=line, end_line=line,
            repository_revision="revision-7",
        ).chunk_id
        for customer, line in (("tenant-a", 1), ("tenant-b", 1), ("tenant-a", 2))
    }
    assert len(values) == 3


@pytest.mark.parametrize("path", ["/tmp/file.py", "../file.py", "src/../file.py", "src\\file.py", ""])
def test_chunk_rejects_unsafe_or_non_posix_source_paths(path: str) -> None:
    with pytest.raises(ValueError, match="source_path"):
        SemanticChunk.create(
            scope=scope(), source_path=path, kind="source", content="x = 1",
            start_line=1, end_line=1, repository_revision="revision-7", language_id="python",
        )


def test_chunk_rejects_invalid_boundaries_and_incomplete_source_metadata() -> None:
    common = dict(
        scope=scope(), source_path="src/file.py", kind="source", content="x = 1",
        repository_revision="revision-7",
    )
    with pytest.raises(ValueError, match="line range"):
        SemanticChunk.create(**common, start_line=2, end_line=1, language_id="python")
    with pytest.raises(ValueError, match="language_id"):
        SemanticChunk.create(**common, start_line=1, end_line=1)
    with pytest.raises(ValueError, match="content"):
        SemanticChunk.create(
            **{**common, "content": ""}, start_line=1, end_line=1, language_id="python"
        )
