from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentic_platform.domain.models import (
    Evidence,
    FrameworkRule,
    RuleOrigin,
    RuleStatus,
)
from agentic_platform.framework_knowledge.snapshots import (
    FrameworkKnowledgeSnapshot,
    SnapshotMetadata,
)


def _rule(kind: str = "service.base_class", value: str = "Base") -> FrameworkRule:
    return FrameworkRule(
        kind=kind,
        expected_value=value,
        confidence=1.0,
        support_count=3,
        conflict_count=0,
        evidence=(Evidence("a.py", "Svc", value),),
        metadata={"import_module": "framework"},
        origin=RuleOrigin.DETERMINISTIC_INFERRED,
        status=RuleStatus.ACTIVE,
        framework_version="1.0",
        discovered_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )


class TestSnapshotMetadata:
    def test_metadata_is_immutable(self) -> None:
        meta = SnapshotMetadata(
            repository_revision="abc123",
            parser_version="python-ast-1",
            rule_count=5,
            created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            meta.rule_count = 99  # type: ignore[misc]

    def test_metadata_is_frozen(self) -> None:
        meta = SnapshotMetadata(
            repository_revision="abc123",
            parser_version="python-ast-1",
            rule_count=5,
            created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            meta.repository_revision = "tampered"  # type: ignore[misc]


class TestFrameworkKnowledgeSnapshot:
    def test_snapshot_contains_rules_and_metadata(self) -> None:
        rule = _rule()
        meta = SnapshotMetadata(
            repository_revision="abc123",
            parser_version="python-ast-1",
            rule_count=1,
            created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        snapshot = FrameworkKnowledgeSnapshot(metadata=meta, rules=(rule,))
        assert snapshot.rules == (rule,)
        assert snapshot.metadata == meta

    def test_snapshot_is_immutable(self) -> None:
        rule = _rule()
        meta = SnapshotMetadata(
            repository_revision="abc123",
            parser_version="python-ast-1",
            rule_count=1,
            created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        snapshot = FrameworkKnowledgeSnapshot(metadata=meta, rules=(rule,))
        with pytest.raises(AttributeError):
            snapshot.rules = ()  # type: ignore[misc]

    def test_snapshot_created_from_rules(self) -> None:
        rules = (_rule("service.base_class", "Base"), _rule("service.required_decorator", "managed"))
        snapshot = FrameworkKnowledgeSnapshot.from_rules(
            rules=rules,
            repository_revision="abc123",
            parser_version="python-ast-1",
        )
        assert len(snapshot.rules) == 2
        assert snapshot.metadata.repository_revision == "abc123"
        assert snapshot.metadata.parser_version == "python-ast-1"
        assert snapshot.metadata.rule_count == 2
        assert snapshot.metadata.created_at.tzinfo is not None  # timezone-aware

    def test_snapshot_preserves_rule_order(self) -> None:
        rules = (
            _rule("service.base_class", "Base"),
            _rule("service.required_decorator", "managed"),
            _rule("dependency.constructor", "client"),
        )
        snapshot = FrameworkKnowledgeSnapshot.from_rules(
            rules=rules,
            repository_revision="abc123",
            parser_version="python-ast-1",
        )
        assert [r.kind for r in snapshot.rules] == [
            "service.base_class",
            "service.required_decorator",
            "dependency.constructor",
        ]

    def test_empty_snapshot_allowed(self) -> None:
        snapshot = FrameworkKnowledgeSnapshot.from_rules(
            rules=(),
            repository_revision="empty",
            parser_version="python-ast-1",
        )
        assert snapshot.rules == ()
        assert snapshot.metadata.rule_count == 0

    def test_snapshot_has_unique_identity(self) -> None:
        rule = _rule()
        meta = SnapshotMetadata(
            repository_revision="abc123",
            parser_version="python-ast-1",
            rule_count=1,
            created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        snapshot = FrameworkKnowledgeSnapshot(metadata=meta, rules=(rule,))
        # Each snapshot should have a unique identity (e.g., based on content hash)
        assert snapshot.identity

    def test_same_content_produces_same_identity(self) -> None:
        rule = _rule()
        meta = SnapshotMetadata(
            repository_revision="abc123",
            parser_version="python-ast-1",
            rule_count=1,
            created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        s1 = FrameworkKnowledgeSnapshot(metadata=meta, rules=(rule,))
        s2 = FrameworkKnowledgeSnapshot(metadata=meta, rules=(rule,))
        assert s1.identity == s2.identity

    def test_different_content_produces_different_identity(self) -> None:
        rule1 = _rule("service.base_class", "Base")
        rule2 = _rule("service.base_class", "Other")
        meta = SnapshotMetadata(
            repository_revision="abc123",
            parser_version="python-ast-1",
            rule_count=1,
            created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        s1 = FrameworkKnowledgeSnapshot(metadata=meta, rules=(rule1,))
        s2 = FrameworkKnowledgeSnapshot(metadata=meta, rules=(rule2,))
        assert s1.identity != s2.identity
