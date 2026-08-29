"""Immutable source and document chunks for semantic indexing."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import PurePosixPath
from typing import Mapping

from agentic_platform.domain.models import KnowledgeScope


class ChunkKind(StrEnum):
    """Repository content families accepted by the semantic index."""

    SOURCE = "source"
    DOCUMENT = "document"


@dataclass(frozen=True)
class SemanticChunk:
    """Content-addressed repository excerpt with mandatory tenant scope."""

    chunk_id: str
    scope: KnowledgeScope
    source_path: str
    kind: ChunkKind
    content: str
    content_hash: str
    start_line: int
    end_line: int
    repository_revision: str
    language_id: str | None = None
    symbol: str | None = None

    @classmethod
    def create(
        cls,
        *,
        scope: KnowledgeScope,
        source_path: str,
        kind: ChunkKind | str,
        content: str,
        start_line: int,
        end_line: int,
        repository_revision: str,
        language_id: str | None = None,
        symbol: str | None = None,
    ) -> SemanticChunk:
        """Validate a chunk and derive identities without provider state."""
        _validate_relative_posix_path(source_path)
        try:
            normalized_kind = ChunkKind(kind)
        except ValueError as exc:
            raise ValueError("kind must be source or document") from exc
        if not isinstance(content, str) or not content:
            raise ValueError("content must be a non-empty string")
        if (
            not isinstance(start_line, int)
            or isinstance(start_line, bool)
            or not isinstance(end_line, int)
            or isinstance(end_line, bool)
            or start_line < 1
            or end_line < start_line
        ):
            raise ValueError("line range must be positive and ordered")
        _require_optional_text("language_id", language_id)
        _require_optional_text("symbol", symbol)
        if normalized_kind is ChunkKind.SOURCE and language_id is None:
            raise ValueError("language_id is required for source chunks")
        if not isinstance(repository_revision, str) or not repository_revision.strip():
            raise ValueError("repository_revision must be a non-empty string")

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        identity = {
            "scope": scope.hierarchy,
            "source_path": source_path,
            "kind": normalized_kind.value,
            "content_hash": content_hash,
            "start_line": start_line,
            "end_line": end_line,
            "repository_revision": repository_revision,
            "language_id": language_id,
            "symbol": symbol,
        }
        chunk_id = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            chunk_id=chunk_id,
            scope=scope,
            source_path=source_path,
            kind=normalized_kind,
            content=content,
            content_hash=content_hash,
            start_line=start_line,
            end_line=end_line,
            repository_revision=repository_revision,
            language_id=language_id,
            symbol=symbol,
        )

    @property
    def filter_metadata(self) -> Mapping[str, str | None]:
        """Provider-neutral metadata for mandatory filtered retrieval."""
        return {
            "customer_id": self.scope.customer_id,
            "framework_id": self.scope.framework_id,
            "framework_version_id": self.scope.framework_version_id,
            "project_id": self.scope.project_id,
            "module_id": self.scope.module_id,
            "kind": self.kind.value,
            "source_path": self.source_path,
            "language_id": self.language_id,
            "repository_revision": self.repository_revision,
        }


def _validate_relative_posix_path(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value.startswith("/")
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or PurePosixPath(value).is_absolute()
    ):
        raise ValueError("source_path must be a safe relative POSIX path")


def _require_optional_text(name: str, value: str | None) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be None or a non-empty string")
