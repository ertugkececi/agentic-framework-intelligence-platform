from pathlib import Path

import pytest

from agentic_platform.domain.models import FrameworkRule, KnowledgeScope, RuleStatus
from agentic_platform.framework_knowledge.sqlite_store import SQLiteKnowledgeStore


def _scope() -> KnowledgeScope:
    return KnowledgeScope("tenant", "framework", "2.0", "project", "api")


def _rule(status: RuleStatus = RuleStatus.CANDIDATE) -> FrameworkRule:
    return FrameworkRule(
        kind="service.base_class",
        expected_value="FrameworkBase",
        confidence=0.9,
        support_count=4,
        conflict_count=0,
        evidence=(),
        status=status,
    )


def test_rule_status_supports_complete_lifecycle_and_rejects_unknown_values() -> None:
    assert {status.value for status in RuleStatus} == {
        "candidate", "active", "rejected", "superseded", "deprecated"
    }
    assert FrameworkRule(**{**_rule().__dict__, "status": "active"}).status is RuleStatus.ACTIVE
    with pytest.raises(ValueError, match="status"):
        FrameworkRule(**{**_rule().__dict__, "status": "unknown"})


def test_sqlite_transitions_rules_within_scope_and_enforces_lifecycle(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
    scope = _scope()
    try:
        store.replace_rules([_rule()], scope=scope)
        activated = store.transition_rule_status(
            "service.base_class", "FrameworkBase", RuleStatus.ACTIVE, scope=scope
        )
        deprecated = store.transition_rule_status(
            "service.base_class", "FrameworkBase", RuleStatus.DEPRECATED, scope=scope
        )

        assert activated.status is RuleStatus.ACTIVE
        assert deprecated.status is RuleStatus.DEPRECATED
        assert store.active_rules_for("service", scope=scope) == []
        with pytest.raises(ValueError, match="terminal"):
            store.transition_rule_status(
                "service.base_class", "FrameworkBase", RuleStatus.ACTIVE, scope=scope
            )
    finally:
        store.close()


def test_sqlite_transition_is_fail_closed_for_scope_and_missing_rule(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
    try:
        store.replace_rules([_rule()], scope=_scope())
        with pytest.raises(ValueError, match="explicit scope"):
            store.transition_rule_status(
                "service.base_class", "FrameworkBase", RuleStatus.ACTIVE
            )
        with pytest.raises(LookupError, match="rule not found"):
            store.transition_rule_status(
                "service.base_class", "FrameworkBase", RuleStatus.ACTIVE,
                scope=KnowledgeScope("other", "framework", "2.0", "project", "api"),
            )
    finally:
        store.close()
