"""Qdrant REST adapter for scope-isolated semantic vectors."""
from __future__ import annotations

import json
import math
import re
from typing import Any, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.retrieval.semantic_chunks import (
    ChunkKind,
    SemanticChunk,
    _validate_relative_posix_path,
)
from agentic_platform.retrieval.semantic_store import SemanticMatch, VectorEntry
from agentic_platform.security.policy import Capability, CapabilityGrant


class QdrantHttpError(RuntimeError):
    """Sanitized Qdrant HTTP failure retaining only the response status."""

    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"Qdrant request failed with HTTP {status}")


class QdrantTransport(Protocol):
    """Minimal JSON transport boundary, injectable for on-prem clients."""

    def request(
        self, method: str, path: str, payload: dict[str, Any]
    ) -> Mapping[str, Any]: ...


class QdrantHttpTransport:
    """Small stdlib HTTP transport that does not leak credentials in payloads."""

    def __init__(self, base_url: str, *, api_key: str | None = None, timeout: float = 30.0) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("base_url must be an absolute HTTP(S) URL without query or fragment")
        if api_key is not None and not api_key:
            raise ValueError("api_key must be None or a non-empty string")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = float(timeout)

    def request(
        self, method: str, path: str, payload: dict[str, Any]
    ) -> Mapping[str, Any]:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key is not None:
            headers["api-key"] = self._api_key
        request = Request(self._base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self._timeout) as response:  # nosec B310: URL validated above
                decoded = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise QdrantHttpError(exc.code) from exc
        except URLError as exc:
            raise RuntimeError("Qdrant request failed") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("Qdrant returned a non-object JSON response")
        return decoded


class QdrantSemanticStore:
    """Production vector adapter with mandatory scope metadata on every point."""

    def __init__(
        self,
        transport: QdrantTransport,
        *,
        grant: CapabilityGrant,
        collection_name: str,
        vector_size: int,
        initialize_collection: bool = True,
    ) -> None:
        if not isinstance(grant, CapabilityGrant):
            raise TypeError("grant must be a CapabilityGrant")
        if not isinstance(collection_name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", collection_name):
            raise ValueError("collection_name must contain only letters, digits, underscore, or hyphen")
        if not isinstance(vector_size, int) or isinstance(vector_size, bool) or vector_size < 1:
            raise ValueError("vector_size must be a positive integer")
        self._transport = transport
        self._grant = grant
        self._collection_name = collection_name
        self._vector_size = vector_size
        if initialize_collection:
            self._grant.require(Capability.DATABASE_WRITE)
            try:
                self._transport.request(
                    "PUT",
                    self._collection_path,
                    {"vectors": {"size": vector_size, "distance": "Cosine"}},
                )
            except QdrantHttpError as exc:
                if exc.status != 409:
                    raise
                response = self._transport.request("GET", self._collection_path, {})
                try:
                    existing_size = response["result"]["config"]["params"]["vectors"]["size"]
                except (KeyError, TypeError):
                    raise RuntimeError("Qdrant collection response is malformed") from None
                if existing_size != vector_size:
                    raise ValueError("existing Qdrant collection vector dimension mismatch")

    @classmethod
    def from_url(
        cls,
        base_url: str,
        *,
        grant: CapabilityGrant,
        collection_name: str,
        vector_size: int,
        api_key: str | None = None,
        timeout: float = 30.0,
        initialize_collection: bool = True,
    ) -> "QdrantSemanticStore":
        if not isinstance(grant, CapabilityGrant):
            raise TypeError("grant must be a CapabilityGrant")
        if initialize_collection:
            grant.require(Capability.DATABASE_WRITE)
        return cls(
            QdrantHttpTransport(base_url, api_key=api_key, timeout=timeout),
            grant=grant,
            collection_name=collection_name,
            vector_size=vector_size,
            initialize_collection=initialize_collection,
        )

    @property
    def _collection_path(self) -> str:
        return f"/collections/{self._collection_name}"

    def upsert(self, entries: Sequence[VectorEntry]) -> None:
        self._grant.require(Capability.DATABASE_WRITE)
        for chunk, _ in entries:
            self._grant.require_scope(chunk.scope)
        points = self._points(entries)
        if points:
            self._transport.request(
                "PUT", f"{self._collection_path}/points?wait=true", {"points": points}
            )

    def _points(self, entries: Sequence[VectorEntry]) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for chunk, raw_vector in entries:
            vector = self._validate_vector(raw_vector)
            payload = {
                **chunk.filter_metadata,
                "chunk_id": chunk.chunk_id,
                "content_hash": chunk.content_hash,
                "content": chunk.content,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "symbol": chunk.symbol,
            }
            points.append({
                "id": str(uuid5(NAMESPACE_URL, chunk.chunk_id)),
                "vector": vector,
                "payload": payload,
            })
        return points

    def replace_source_chunks(
        self, scope: KnowledgeScope, entries: Sequence[VectorEntry]
    ) -> None:
        """Replace every source point in exactly one authorized scope."""
        self._grant.require(Capability.DATABASE_WRITE)
        self._grant.require_scope(scope)
        validated = tuple(entries)
        for chunk, vector in validated:
            if chunk.scope != scope or chunk.kind is not ChunkKind.SOURCE:
                raise PermissionError("source replacement entry is outside the requested scope")
            self._validate_vector(vector)
        points = self._points(validated)
        must = self._scope_filter(scope)
        must.append({"key": "kind", "match": {"value": ChunkKind.SOURCE.value}})
        operations: list[dict[str, Any]] = [
            {"delete": {"filter": {"must": must}}}
        ]
        if points:
            operations.append({"upsert": {"points": points}})
        self._transport.request(
            "POST",
            f"{self._collection_path}/points/batch?wait=true",
            {"operations": operations},
        )

    def search(
        self,
        scope: KnowledgeScope,
        query_vector: Sequence[float],
        *,
        limit: int,
        kind: ChunkKind | str | None = None,
    ) -> tuple[SemanticMatch, ...]:
        """Return only payloads validated against the complete requested scope."""
        self._grant.require(Capability.DATABASE_READ)
        self._grant.require_scope(scope)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        vector = self._validate_vector(query_vector)
        normalized_kind: ChunkKind | None = None
        if kind is not None:
            try:
                normalized_kind = ChunkKind(kind)
            except ValueError as exc:
                raise ValueError("kind must be source or document") from exc
        must = self._scope_filter(scope)
        if normalized_kind is not None:
            must.append({"key": "kind", "match": {"value": normalized_kind.value}})
        response = self._transport.request(
            "POST",
            f"{self._collection_path}/points/search",
            {
                "vector": vector,
                "filter": {"must": must},
                "limit": limit,
                "with_payload": True,
                "with_vector": False,
            },
        )
        results = response.get("result")
        if not isinstance(results, list):
            raise RuntimeError("Qdrant search response is malformed")
        matches: list[SemanticMatch] = []
        for result in results:
            try:
                if not isinstance(result, Mapping):
                    raise ValueError
                score = result["score"]
                payload = result["payload"]
                if (
                    isinstance(score, bool)
                    or not isinstance(score, (int, float))
                    or not math.isfinite(score)
                    or not isinstance(payload, Mapping)
                ):
                    raise ValueError
                chunk = self._chunk_from_payload(payload, scope)
                if normalized_kind is not None and chunk.kind is not normalized_kind:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                raise RuntimeError("Qdrant search response is malformed or outside scope") from None
            matches.append(SemanticMatch(chunk=chunk, score=float(score)))
        return tuple(matches)

    def _validate_vector(self, raw_vector: Sequence[float]) -> list[float]:
        vector = list(raw_vector)
        if len(vector) != self._vector_size:
            raise ValueError(f"vector dimension must be {self._vector_size}")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in vector
        ):
            raise ValueError("vector values must be finite numbers")
        return vector

    @staticmethod
    def _scope_filter(scope: KnowledgeScope) -> list[dict[str, Any]]:
        must: list[dict[str, Any]] = [
            {"key": key, "match": {"value": value}}
            for key, value in zip(
                ("customer_id", "framework_id", "framework_version_id", "project_id"),
                scope.hierarchy[:4],
                strict=True,
            )
        ]
        if scope.module_id is None:
            must.append({"is_null": {"key": "module_id"}})
        else:
            must.append({"key": "module_id", "match": {"value": scope.module_id}})
        return must

    @staticmethod
    def _chunk_from_payload(payload: Mapping[str, Any], scope: KnowledgeScope) -> SemanticChunk:
        expected_scope = {
            "customer_id": scope.customer_id,
            "framework_id": scope.framework_id,
            "framework_version_id": scope.framework_version_id,
            "project_id": scope.project_id,
            "module_id": scope.module_id,
        }
        if any(payload.get(key) != value for key, value in expected_scope.items()):
            raise ValueError("payload scope mismatch")
        chunk = SemanticChunk.create(
            scope=scope,
            source_path=payload["source_path"],
            kind=payload["kind"],
            content=payload["content"],
            start_line=payload["start_line"],
            end_line=payload["end_line"],
            repository_revision=payload["repository_revision"],
            language_id=payload.get("language_id"),
            symbol=payload.get("symbol"),
        )
        if payload.get("chunk_id") != chunk.chunk_id or payload.get("content_hash") != chunk.content_hash:
            raise ValueError("payload identity mismatch")
        return chunk

    def delete_source(self, scope: KnowledgeScope, source_path: str) -> None:
        self._grant.require(Capability.DATABASE_WRITE)
        self._grant.require_scope(scope)
        _validate_relative_posix_path(source_path)
        must = self._scope_filter(scope)
        must.append({"key": "source_path", "match": {"value": source_path}})
        self._transport.request(
            "POST",
            f"{self._collection_path}/points/delete?wait=true",
            {"filter": {"must": must}},
        )
