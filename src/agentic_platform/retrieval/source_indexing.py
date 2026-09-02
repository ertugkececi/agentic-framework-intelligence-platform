"""Scoped extraction and incremental persistence of repository source chunks."""
from __future__ import annotations

import ast
import math
from pathlib import Path
from typing import Protocol, Sequence

from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.framework_learning.inventory import RepositoryRevision, RepositoryScanner
from agentic_platform.framework_learning.python_ast import PythonAstParser
from agentic_platform.retrieval.semantic_chunks import SemanticChunk
from agentic_platform.retrieval.embeddings import EmbeddingProvider
from agentic_platform.retrieval.semantic_store import VectorEntry
from agentic_platform.security.policy import Capability, CapabilityGrant
from agentic_platform.security.secrets import SecretRedactor


class RepositorySourceChunkExtractor:
    """Create source chunks from inventoried, parser-validated Python symbols."""

    def __init__(self, *, grant: CapabilityGrant) -> None:
        if not isinstance(grant, CapabilityGrant):
            raise TypeError("grant must be a CapabilityGrant")
        self._grant = grant

    def extract(
        self, repository: Path, scope: KnowledgeScope
    ) -> tuple[SemanticChunk, ...]:
        if not isinstance(scope, KnowledgeScope):
            raise TypeError("scope must be a KnowledgeScope")
        self._grant.require(Capability.READ_REPOSITORY)
        self._grant.require_repository(repository)
        self._grant.require_scope(scope)
        inventory = RepositoryScanner().scan(repository)
        revision = RepositoryRevision.from_inventory(inventory).value
        parser = PythonAstParser()
        redactor = SecretRedactor()
        chunks: list[SemanticChunk] = []
        for source_file in inventory.files:
            parsed = parser.parse(repository, source_file)
            source = (repository / source_file.relative_path).read_text(encoding="utf-8")
            for node in parsed.module.body:
                if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                content = ast.get_source_segment(source, node)
                if not content or node.end_lineno is None:
                    continue
                chunks.append(
                    SemanticChunk.create(
                        scope=scope,
                        source_path=source_file.relative_path,
                        kind="source",
                        content=redactor.redact(content),
                        start_line=node.lineno,
                        end_line=node.end_lineno,
                        repository_revision=revision,
                        language_id=source_file.language_id,
                        symbol=node.name,
                    )
                )
        return tuple(chunks)


class SourceChunkStore(Protocol):
    """Atomic logical replacement boundary for one scope's source chunks."""

    def replace_source_chunks(
        self, scope: KnowledgeScope, entries: Sequence[VectorEntry]
    ) -> None: ...


class RepositorySemanticIndexer:
    """Extract, embed, validate, then replace one scope's source index."""

    def __init__(
        self,
        *,
        grant: CapabilityGrant,
        extractor: RepositorySourceChunkExtractor,
        embedding: EmbeddingProvider,
        store: SourceChunkStore,
    ) -> None:
        if not isinstance(grant, CapabilityGrant):
            raise TypeError("grant must be a CapabilityGrant")
        self._grant = grant
        self._extractor = extractor
        self._embedding = embedding
        self._store = store

    def index(self, repository: Path, scope: KnowledgeScope) -> int:
        if not isinstance(scope, KnowledgeScope):
            raise TypeError("scope must be a KnowledgeScope")
        self._grant.require(Capability.READ_REPOSITORY)
        self._grant.require(Capability.DATABASE_WRITE)
        self._grant.require_repository(repository)
        self._grant.require_scope(scope)
        chunks = self._extractor.extract(repository, scope)
        vectors = self._embedding.embed(tuple(chunk.content for chunk in chunks))
        if len(vectors) != len(chunks):
            raise ValueError("embedding provider returned the wrong vector count")
        for vector in vectors:
            if len(vector) != self._embedding.dimension:
                raise ValueError("embedding provider returned a malformed dimension")
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            ):
                raise ValueError("embedding provider returned non-finite values")
        entries = tuple(zip(chunks, vectors, strict=True))
        self._store.replace_source_chunks(scope, entries)
        return len(entries)
