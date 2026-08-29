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
from agentic_platform.retrieval.semantic_chunks import SemanticChunk, _validate_relative_posix_path
from agentic_platform.retrieval.semantic_store import VectorEntry


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
            raise RuntimeError(f"Qdrant request failed with HTTP {exc.code}") from exc
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
        collection_name: str,
        vector_size: int,
        initialize_collection: bool = True,
    ) -> None:
        if not isinstance(collection_name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", collection_name):
            raise ValueError("collection_name must contain only letters, digits, underscore, or hyphen")
        if not isinstance(vector_size, int) or isinstance(vector_size, bool) or vector_size < 1:
            raise ValueError("vector_size must be a positive integer")
        self._transport = transport
        self._collection_name = collection_name
        self._vector_size = vector_size
        if initialize_collection:
            self._transport.request(
                "PUT",
                self._collection_path,
                {"vectors": {"size": vector_size, "distance": "Cosine"}},
            )

    @classmethod
    def from_url(
        cls,
        base_url: str,
        *,
        collection_name: str,
        vector_size: int,
        api_key: str | None = None,
        timeout: float = 30.0,
        initialize_collection: bool = True,
    ) -> "QdrantSemanticStore":
        return cls(
            QdrantHttpTransport(base_url, api_key=api_key, timeout=timeout),
            collection_name=collection_name,
            vector_size=vector_size,
            initialize_collection=initialize_collection,
        )

    @property
    def _collection_path(self) -> str:
        return f"/collections/{self._collection_name}"

    def upsert(self, entries: Sequence[VectorEntry]) -> None:
        points: list[dict[str, Any]] = []
        for chunk, raw_vector in entries:
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
        if points:
            self._transport.request(
                "PUT", f"{self._collection_path}/points?wait=true", {"points": points}
            )

    def delete_source(self, scope: KnowledgeScope, source_path: str) -> None:
        _validate_relative_posix_path(source_path)
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
        must.append({"key": "source_path", "match": {"value": source_path}})
        self._transport.request(
            "POST",
            f"{self._collection_path}/points/delete?wait=true",
            {"filter": {"must": must}},
        )
