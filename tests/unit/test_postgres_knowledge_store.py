from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from agentic_platform.domain.models import Evidence, FrameworkRule, KnowledgeScope, RuleStatus
from agentic_platform.framework_knowledge.postgres_store import PostgresKnowledgeStore
from agentic_platform.framework_knowledge.store import RuleKnowledgeStore
from agentic_platform.security.policy import Capability, CapabilityGrant


class RecordingCursor:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, object]] = []

    def execute(self, statement: str, parameters: object = None) -> None:
        self.calls.append((statement, parameters))

    def executemany(self, statement: str, parameters: object) -> None:
        self.calls.append((statement, parameters))

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


class RecordingConnection:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.cursor_instance = RecordingCursor(rows)
        self.transactions = 0
        self.closed = False

    @contextmanager
    def cursor(self) -> Iterator[RecordingCursor]:
        yield self.cursor_instance

    def __enter__(self) -> RecordingConnection:
        self.transactions += 1
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _database_grant(*capabilities: Capability) -> CapabilityGrant:
    allowed = capabilities or (Capability.DATABASE_READ, Capability.DATABASE_WRITE)
    return CapabilityGrant(frozenset(allowed), Path.cwd())


def _scope(module: str | None = "api") -> KnowledgeScope:
    return KnowledgeScope("tenant", "framework", "2.0", "project", module)


def _rule(scope: KnowledgeScope | None = None) -> FrameworkRule:
    return FrameworkRule(
        kind="service.base_class",
        expected_value="FrameworkBase",
        confidence=0.9,
        support_count=4,
        conflict_count=1,
        evidence=(Evidence("app/service.py", "OrderService", "extends FrameworkBase"),),
        metadata={"import_module": "framework.core"},
        status=RuleStatus.ACTIVE,
        scope=scope,
    )


def test_postgres_adapter_satisfies_shared_rule_store_port_and_creates_jsonb_schema() -> None:
    connection = RecordingConnection()

    store: RuleKnowledgeStore = PostgresKnowledgeStore(connection, grant=_database_grant())

    schema = connection.cursor_instance.calls[0][0]
    assert "CREATE TABLE IF NOT EXISTS framework_rule" in schema
    assert schema.count("JSONB") >= 2
    assert "customer_id TEXT NOT NULL" in schema
    store.close()
    assert connection.closed


def test_postgres_replace_is_atomic_scoped_and_serializes_jsonb() -> None:
    connection = RecordingConnection()
    store = PostgresKnowledgeStore(connection, grant=_database_grant())
    scope = _scope()
    transactions_after_schema = connection.transactions

    store.replace_rules([_rule()], repository_identity="revision", scope=scope)

    delete_sql, delete_parameters = connection.cursor_instance.calls[1]
    insert_sql, batches = connection.cursor_instance.calls[-1]
    assert connection.transactions == transactions_after_schema + 1
    assert "IS NOT DISTINCT FROM" in delete_sql
    assert delete_parameters == scope.hierarchy
    assert "::jsonb" in insert_sql
    row = list(batches)[0]
    assert json.loads(row[9])[0]["source_path"] == "app/service.py"
    assert json.loads(row[10]) == {"import_module": "framework.core"}
    assert row[-5:] == scope.hierarchy


def test_postgres_rejects_unscoped_or_mismatched_writes() -> None:
    store = PostgresKnowledgeStore(RecordingConnection(), grant=_database_grant())
    scope = _scope()

    with pytest.raises(ValueError, match="explicit scope"):
        store.replace_rules([_rule()])
    with pytest.raises(ValueError, match="does not match"):
        store.replace_rules([_rule(_scope("other"))], scope=scope)


def test_postgres_active_rule_query_round_trips_jsonb_and_scope() -> None:
    scope = _scope(None)
    rule = _rule(scope)
    row = {
        "kind": rule.kind,
        "expected_value": rule.expected_value,
        "confidence": rule.confidence,
        "support_count": rule.support_count,
        "conflict_count": rule.conflict_count,
        "evidence_json": [item.__dict__ for item in rule.evidence],
        "metadata_json": dict(rule.metadata),
        "origin": str(rule.origin),
        "status": str(rule.status),
        "framework_version": rule.framework_version,
        "discovered_at": rule.discovered_at,
        "customer_id": scope.customer_id,
        "framework_id": scope.framework_id,
        "framework_version_id": scope.framework_version_id,
        "project_id": scope.project_id,
        "module_id": scope.module_id,
    }
    connection = RecordingConnection([row])
    store = PostgresKnowledgeStore(connection, grant=_database_grant())

    result = store.active_rules_for("service", scope=scope)

    query, parameters = connection.cursor_instance.calls[-1]
    assert "IS NOT DISTINCT FROM" in query
    assert parameters == ("active", "service.%", *scope.hierarchy)
    assert result == [rule]
    with pytest.raises(ValueError, match="explicit scope"):
        store.active_rules_for("service")

def test_postgres_rule_transition_is_atomic_and_scope_filtered() -> None:
    scope = _scope()
    rule = _rule(scope)
    row = {
        "id": 7, "kind": rule.kind, "expected_value": rule.expected_value,
        "confidence": rule.confidence, "support_count": rule.support_count,
        "conflict_count": rule.conflict_count,
        "evidence_json": [item.__dict__ for item in rule.evidence],
        "metadata_json": dict(rule.metadata), "origin": str(rule.origin),
        "status": "candidate", "framework_version": rule.framework_version,
        "discovered_at": rule.discovered_at, "customer_id": scope.customer_id,
        "framework_id": scope.framework_id,
        "framework_version_id": scope.framework_version_id,
        "project_id": scope.project_id, "module_id": scope.module_id,
    }
    connection = RecordingConnection([row])
    store = PostgresKnowledgeStore(connection, grant=_database_grant())

    transitioned = store.transition_rule_status(
        rule.kind, rule.expected_value, RuleStatus.ACTIVE, scope=scope
    )

    select_call, update_call = connection.cursor_instance.calls[-2:]
    assert "expected_value = %s::jsonb" in select_call[0]
    assert select_call[1] == (rule.kind, json.dumps(rule.expected_value), *scope.hierarchy)
    assert "UPDATE framework_rule SET status" in update_call[0]
    assert update_call[1] == ("active", 7)
    assert transitioned.status is RuleStatus.ACTIVE

    with pytest.raises(ValueError, match="explicit scope"):
        store.transition_rule_status(rule.kind, rule.expected_value, RuleStatus.ACTIVE)


def test_postgres_requires_typed_database_authority_before_schema_initialization() -> None:
    connection = RecordingConnection()

    with pytest.raises(TypeError, match="grant"):
        PostgresKnowledgeStore(connection)
    with pytest.raises(TypeError, match="CapabilityGrant"):
        PostgresKnowledgeStore(connection, grant=None)  # type: ignore[arg-type]

    assert connection.cursor_instance.calls == []


def test_postgres_checks_read_and_write_capabilities_before_database_access() -> None:
    read_connection = RecordingConnection()
    read_only = PostgresKnowledgeStore(
        read_connection, grant=_database_grant(Capability.DATABASE_READ),
        initialize_schema=False,
    )
    with pytest.raises(PermissionError, match="database_write"):
        read_only.replace_rules([_rule()], scope=_scope())
    assert read_connection.cursor_instance.calls == []
    assert read_connection.transactions == 0

    write_connection = RecordingConnection()
    write_only = PostgresKnowledgeStore(
        write_connection, grant=_database_grant(Capability.DATABASE_WRITE),
        initialize_schema=False,
    )
    with pytest.raises(PermissionError, match="database_read"):
        write_only.active_rules_for("service", scope=_scope())
    assert write_connection.cursor_instance.calls == []
    assert write_connection.transactions == 0


def test_postgres_dsn_factory_denies_invalid_or_schema_read_only_grant_before_connect() -> None:
    with pytest.raises(TypeError, match="CapabilityGrant"):
        PostgresKnowledgeStore.from_dsn(
            "postgresql://database.invalid/knowledge", grant=None  # type: ignore[arg-type]
        )
    with pytest.raises(PermissionError, match="database_write"):
        PostgresKnowledgeStore.from_dsn(
            "postgresql://database.invalid/knowledge",
            grant=_database_grant(Capability.DATABASE_READ),
        )
