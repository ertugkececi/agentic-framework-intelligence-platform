"""Immutable framework knowledge snapshots.

A snapshot captures the complete set of framework rules derived from a specific
repository revision. Snapshots are immutable and content-addressed, providing an
auditable history of framework knowledge over time.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from agentic_platform.domain.models import FrameworkRule


@dataclass(frozen=True)
class SnapshotMetadata:
    """Immutable metadata describing when and how a snapshot was produced."""

    repository_revision: str
    parser_version: str
    rule_count: int
    created_at: datetime


@dataclass(frozen=True)
class FrameworkKnowledgeSnapshot:
    """Immutable, content-addressed snapshot of framework knowledge.

    Each snapshot captures the complete set of framework rules for a specific
    repository revision. Snapshots are never mutated; incremental updates
    produce new snapshots.
    """

    metadata: SnapshotMetadata
    rules: tuple[FrameworkRule, ...]

    @property
    def identity(self) -> str:
        """Content-addressed identity based on metadata and rule content."""
        hasher = hashlib.sha256()
        hasher.update(self.metadata.repository_revision.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(self.metadata.parser_version.encode("utf-8"))
        hasher.update(b"\x00")
        for rule in self.rules:
            hasher.update(rule.kind.encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(rule.expected_value.encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(f"{rule.confidence:.6f}".encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(str(rule.support_count).encode("utf-8"))
            hasher.update(b"\x00")
            hasher.update(str(rule.conflict_count).encode("utf-8"))
            hasher.update(b"\x01")
        return hasher.hexdigest()

    @classmethod
    def from_rules(
        cls,
        rules: tuple[FrameworkRule, ...],
        repository_revision: str,
        parser_version: str,
        *,
        created_at: datetime | None = None,
    ) -> FrameworkKnowledgeSnapshot:
        """Create a snapshot from a set of rules."""
        metadata = SnapshotMetadata(
            repository_revision=repository_revision,
            parser_version=parser_version,
            rule_count=len(rules),
            created_at=created_at or datetime.now(timezone.utc),
        )
        return cls(metadata=metadata, rules=rules)
