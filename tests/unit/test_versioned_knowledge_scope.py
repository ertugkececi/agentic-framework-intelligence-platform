from __future__ import annotations

from pathlib import Path

import pytest

from agentic_platform.domain.models import FrameworkRule, KnowledgeScope, RuleStatus
from agentic_platform.framework_knowledge.snapshots import FrameworkKnowledgeSnapshot
from agentic_platform.framework_knowledge.sqlite_store import SQLiteKnowledgeStore


def _active_rule(value: str, scope: KnowledgeScope | None = None) -> FrameworkRule:
    return FrameworkRule(
        kind="service.base_class",
        expected_value=value,
        confidence=1.0,
        support_count=3,
        conflict_count=0,
        evidence=(),
        status=RuleStatus.ACTIVE,
        scope=scope,
    )


def test_knowledge_scope_is_immutable_and_validates_hierarchy() -> None:
    scope = KnowledgeScope("tenant-a", "framework-a", "2.1", "project-a", "module-a")

    assert scope.hierarchy == ("tenant-a", "framework-a", "2.1", "project-a", "module-a")
    with pytest.raises(AttributeError):
        scope.customer_id = "other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="project_id"):
        KnowledgeScope("tenant-a", "framework-a", "2.1", "", None)


def test_sqlite_store_isolates_rules_by_complete_version_scope(tmp_path: Path) -> None:
    tenant_a = KnowledgeScope("tenant-a", "framework", "1.0", "project", "api")
    tenant_b = KnowledgeScope("tenant-b", "framework", "1.0", "project", "api")
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
    try:
        store.replace_rules([_active_rule("BaseA")], scope=tenant_a)
        store.replace_rules([_active_rule("BaseB")], scope=tenant_b)

        rules_a = store.active_rules_for("service", scope=tenant_a)
        rules_b = store.active_rules_for("service", scope=tenant_b)
    finally:
        store.close()

    assert [(rule.expected_value, rule.scope) for rule in rules_a] == [("BaseA", tenant_a)]
    assert [(rule.expected_value, rule.scope) for rule in rules_b] == [("BaseB", tenant_b)]


def test_scoped_replace_does_not_delete_another_scope(tmp_path: Path) -> None:
    module_a = KnowledgeScope("tenant", "framework", "1.0", "project", "module-a")
    module_b = KnowledgeScope("tenant", "framework", "1.0", "project", "module-b")
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
    try:
        store.replace_rules([_active_rule("First")], scope=module_a)
        store.replace_rules([_active_rule("Other")], scope=module_b)
        store.replace_rules([_active_rule("Updated")], scope=module_a)

        assert [rule.expected_value for rule in store.active_rules_for("service", scope=module_a)] == ["Updated"]
        assert [rule.expected_value for rule in store.active_rules_for("service", scope=module_b)] == ["Other"]
    finally:
        store.close()


def test_snapshot_identity_includes_scope_boundary() -> None:
    scope_a = KnowledgeScope("tenant-a", "framework", "1.0", "project")
    scope_b = KnowledgeScope("tenant-b", "framework", "1.0", "project")

    snapshot_a = FrameworkKnowledgeSnapshot.from_rules(
        (_active_rule("Base", scope_a),), "revision", "parser"
    )
    snapshot_b = FrameworkKnowledgeSnapshot.from_rules(
        (_active_rule("Base", scope_b),), "revision", "parser"
    )

    assert snapshot_a.identity != snapshot_b.identity


def test_scoped_rule_write_requires_matching_explicit_scope(tmp_path: Path) -> None:
    scope_a = KnowledgeScope("tenant-a", "framework", "1.0", "project")
    scope_b = KnowledgeScope("tenant-b", "framework", "1.0", "project")
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
    try:
        with pytest.raises(ValueError, match="explicit scope"):
            store.replace_rules([_active_rule("Base", scope_a)])
        with pytest.raises(ValueError, match="does not match"):
            store.replace_rules([_active_rule("Base", scope_a)], scope=scope_b)
    finally:
        store.close()
