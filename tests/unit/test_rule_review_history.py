from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentic_platform.domain.models import (
    Evidence,
    EvidencePolarity,
    KnowledgeScope,
    RuleOrigin,
    RuleReview,
    RuleReviewAction,
)
from agentic_platform.framework_knowledge.postgres_store import PostgresKnowledgeStore
from agentic_platform.framework_knowledge.sqlite_store import SQLiteKnowledgeStore

def _scope() -> KnowledgeScope:
    return KnowledgeScope("tenant", "framework", "2.0", "project", "api")

def _review(action: RuleReviewAction = RuleReviewAction.APPROVE) -> RuleReview:
    return RuleReview(
        rule_kind="service.base_class",
        expected_value="FrameworkBase",
        scope=_scope(),
        action=action,
        actor="reviewer@example.invalid",
        comment="evidence verified",
        replacement={"expected_value": "ReviewedBase"} if action is RuleReviewAction.EDIT else None,
        reviewed_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )

def test_evidence_polarity_and_imported_origin_are_typed() -> None:
    conflict = Evidence("app/service.py", "Svc", "OtherBase", "conflict")
    assert conflict.polarity is EvidencePolarity.CONFLICT
    assert RuleOrigin.IMPORTED.value == "imported"
    with pytest.raises(ValueError, match="polarity"):
        Evidence("a.py", "S", "obs", "unknown")

def test_rule_review_validates_edit_replacement_and_identity() -> None:
    with pytest.raises(ValueError, match="replacement"):
        _review(RuleReviewAction.EDIT).__class__(
            rule_kind="service.base_class", expected_value="FrameworkBase", scope=_scope(),
            action=RuleReviewAction.EDIT, actor="reviewer", replacement=None,
        )
    with pytest.raises(ValueError, match="actor"):
        RuleReview("kind", "value", _scope(), RuleReviewAction.APPROVE, "")

def test_sqlite_review_history_is_append_only_and_scoped(tmp_path: Path) -> None:
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite")
    first = _review()
    second = _review(RuleReviewAction.REJECT)
    try:
        store.append_rule_review(first)
        store.append_rule_review(second)
        assert store.rule_review_history("service.base_class", "FrameworkBase", scope=_scope()) == [first, second]
        other = KnowledgeScope("other", "framework", "2.0", "project", "api")
        assert store.rule_review_history("service.base_class", "FrameworkBase", scope=other) == []
    finally:
        store.close()

class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.rows: list[dict[str, object]] = []

    def execute(self, statement: str, parameters: object = None) -> None:
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows

class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_instance = RecordingCursor()

    @contextmanager
    def cursor(self) -> Iterator[RecordingCursor]:
        yield self.cursor_instance

    def __enter__(self) -> RecordingConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def close(self) -> None:
        return None

def test_postgres_review_history_serializes_jsonb_and_filters_scope() -> None:
    connection = RecordingConnection()
    store = PostgresKnowledgeStore(connection)
    review = _review(RuleReviewAction.EDIT)

    store.append_rule_review(review)
    insert_sql, parameters = connection.cursor_instance.calls[-1]
    assert "INSERT INTO rule_review" in insert_sql
    assert "::jsonb" in insert_sql
    assert parameters[-5:] == _scope().hierarchy

    connection.cursor_instance.rows = [{
        "rule_kind": review.rule_kind, "expected_value": review.expected_value,
        "action": str(review.action), "actor": review.actor, "comment": review.comment,
        "replacement_json": review.replacement, "reviewed_at": review.reviewed_at,
        "customer_id": _scope().customer_id, "framework_id": _scope().framework_id,
        "framework_version_id": _scope().framework_version_id, "project_id": _scope().project_id,
        "module_id": _scope().module_id,
    }]
    assert store.rule_review_history(review.rule_kind, review.expected_value, scope=_scope()) == [review]
