"""PostgreSQL/JSONB production adapter for version-scoped framework rules."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping, Protocol

from agentic_platform.security.policy import Capability, CapabilityGrant

from agentic_platform.domain.models import (
    Evidence, FrameworkRule, KnowledgeScope, RuleReview, RuleStatus,
    validate_rule_status_transition,
)


class DBAPICursor(Protocol):
    def execute(self, statement: str, parameters: object = None) -> None: ...
    def executemany(self, statement: str, parameters: object) -> None: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class DBAPIConnection(Protocol):
    def cursor(self) -> Any: ...
    def __enter__(self) -> "DBAPIConnection": ...
    def __exit__(self, *args: object) -> None: ...
    def close(self) -> None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS framework_rule (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  kind TEXT NOT NULL,
  expected_value JSONB NOT NULL,
  confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  support_count INTEGER NOT NULL CHECK (support_count >= 0),
  conflict_count INTEGER NOT NULL CHECK (conflict_count >= 0),
  origin TEXT NOT NULL,
  status TEXT NOT NULL,
  framework_version TEXT NOT NULL,
  discovered_at TIMESTAMPTZ NOT NULL,
  evidence_json JSONB NOT NULL,
  metadata_json JSONB NOT NULL,
  customer_id TEXT NOT NULL,
  framework_id TEXT NOT NULL,
  framework_version_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  module_id TEXT
);
CREATE INDEX IF NOT EXISTS framework_rule_scope_kind_status_idx
  ON framework_rule
  (customer_id, framework_id, framework_version_id, project_id, module_id, kind, status);
CREATE TABLE IF NOT EXISTS rule_review (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  rule_kind TEXT NOT NULL,
  expected_value JSONB NOT NULL,
  action TEXT NOT NULL,
  actor TEXT NOT NULL,
  comment TEXT NOT NULL,
  replacement_json JSONB,
  reviewed_at TIMESTAMPTZ NOT NULL,
  customer_id TEXT NOT NULL,
  framework_id TEXT NOT NULL,
  framework_version_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  module_id TEXT
);
CREATE INDEX IF NOT EXISTS rule_review_scope_rule_idx
  ON rule_review
  (customer_id, framework_id, framework_version_id, project_id, module_id,
   rule_kind, reviewed_at);
CREATE TABLE IF NOT EXISTS framework_knowledge_metadata (
  customer_id TEXT NOT NULL,
  framework_id TEXT NOT NULL,
  framework_version_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  module_id TEXT,
  repository_fingerprint TEXT NOT NULL,
  UNIQUE NULLS NOT DISTINCT
    (customer_id, framework_id, framework_version_id, project_id, module_id)
);
"""


class PostgresKnowledgeStore:
    """Transactional production store with mandatory complete tenant scope.

    The injected connection must return mapping rows. ``from_dsn`` configures
    psycopg accordingly and keeps the provider dependency outside domain code.
    """

    def __init__(
        self, connection: DBAPIConnection, *, grant: CapabilityGrant,
        initialize_schema: bool = True,
    ) -> None:
        if not isinstance(grant, CapabilityGrant):
            raise TypeError("grant must be a CapabilityGrant")
        self.connection = connection
        self._grant = grant
        if initialize_schema:
            self._grant.require(Capability.DATABASE_WRITE)
            with self.connection:
                with self.connection.cursor() as cursor:
                    cursor.execute(_SCHEMA)

    @classmethod
    def from_dsn(
        cls, dsn: str, *, grant: CapabilityGrant, initialize_schema: bool = True,
    ) -> "PostgresKnowledgeStore":
        if not isinstance(grant, CapabilityGrant):
            raise TypeError("grant must be a CapabilityGrant")
        if initialize_schema:
            grant.require(Capability.DATABASE_WRITE)
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on deployment extras
            raise RuntimeError("PostgreSQL support requires the psycopg dependency") from exc
        return cls(
            psycopg.connect(dsn, row_factory=dict_row),
            grant=grant, initialize_schema=initialize_schema,
        )

    def replace_rules(
        self,
        rules: list[FrameworkRule],
        repository_identity: str | None = None,
        *,
        scope: KnowledgeScope | None = None,
    ) -> None:
        self._grant.require(Capability.DATABASE_WRITE)
        if scope is None:
            raise ValueError("PostgreSQL rule writes require an explicit scope")
        scoped_rules: list[FrameworkRule] = []
        for rule in rules:
            if rule.scope is not None and rule.scope != scope:
                raise ValueError("rule scope does not match replacement scope")
            scoped_rules.append(replace(rule, scope=scope))

        with self.connection:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """DELETE FROM framework_rule
                    WHERE customer_id = %s AND framework_id = %s
                      AND framework_version_id = %s AND project_id = %s
                      AND module_id IS NOT DISTINCT FROM %s""",
                    scope.hierarchy,
                )
                if repository_identity is not None:
                    cursor.execute(
                        """INSERT INTO framework_knowledge_metadata
                        (customer_id, framework_id, framework_version_id, project_id,
                         module_id, repository_fingerprint)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (customer_id, framework_id, framework_version_id,
                                     project_id, module_id)
                        DO UPDATE SET repository_fingerprint = EXCLUDED.repository_fingerprint""",
                        (*scope.hierarchy, repository_identity),
                    )
                cursor.executemany(
                    """INSERT INTO framework_rule
                    (kind, expected_value, confidence, support_count, conflict_count,
                     origin, status, framework_version, discovered_at, evidence_json,
                     metadata_json, customer_id, framework_id, framework_version_id,
                     project_id, module_id)
                    VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s,
                            %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)""",
                    [self._rule_parameters(rule) for rule in scoped_rules],
                )

    def append_rule_review(self, review: RuleReview) -> None:
        """Append one immutable review event within its mandatory tenant scope."""
        self._grant.require(Capability.DATABASE_WRITE)
        with self.connection:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO rule_review
                    (rule_kind, expected_value, action, actor, comment, replacement_json,
                     reviewed_at, customer_id, framework_id, framework_version_id,
                     project_id, module_id)
                    VALUES (%s, %s::jsonb, %s, %s, %s, %s::jsonb, %s,
                            %s, %s, %s, %s, %s)""",
                    (
                        review.rule_kind,
                        json.dumps(review.expected_value),
                        str(review.action),
                        review.actor,
                        review.comment,
                        json.dumps(dict(review.replacement)) if review.replacement is not None else None,
                        review.reviewed_at,
                        *review.scope.hierarchy,
                    ),
                )

    def rule_review_history(
        self, rule_kind: str, expected_value: str, *, scope: KnowledgeScope,
    ) -> list[RuleReview]:
        self._grant.require(Capability.DATABASE_READ)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT rule_kind, expected_value, action, actor, comment,
                          replacement_json, reviewed_at, customer_id, framework_id,
                          framework_version_id, project_id, module_id
                   FROM rule_review
                   WHERE rule_kind = %s AND expected_value = %s::jsonb
                     AND customer_id = %s AND framework_id = %s
                     AND framework_version_id = %s AND project_id = %s
                     AND module_id IS NOT DISTINCT FROM %s
                   ORDER BY reviewed_at, id""",
                (rule_kind, json.dumps(expected_value), *scope.hierarchy),
            )
            return [self._to_review(row) for row in cursor.fetchall()]

    def transition_rule_status(
        self,
        rule_kind: str,
        expected_value: str,
        target_status: RuleStatus,
        *,
        scope: KnowledgeScope | None = None,
    ) -> FrameworkRule:
        """Atomically move one production rule through the scoped lifecycle."""
        self._grant.require(Capability.DATABASE_READ)
        self._grant.require(Capability.DATABASE_WRITE)
        if scope is None:
            raise ValueError("rule status transitions require an explicit scope")
        try:
            target = RuleStatus(target_status)
        except ValueError as exc:
            raise ValueError("target_status must be a recognized rule lifecycle status") from exc
        with self.connection:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """SELECT id, kind, expected_value, confidence, support_count,
                              conflict_count, origin, status, framework_version,
                              discovered_at, evidence_json, metadata_json,
                              customer_id, framework_id, framework_version_id,
                              project_id, module_id
                       FROM framework_rule
                       WHERE kind = %s AND expected_value = %s::jsonb
                         AND customer_id = %s AND framework_id = %s
                         AND framework_version_id = %s AND project_id = %s
                         AND module_id IS NOT DISTINCT FROM %s
                       FOR UPDATE""",
                    (rule_kind, json.dumps(expected_value), *scope.hierarchy),
                )
                rows = cursor.fetchall()
                if not rows:
                    raise LookupError("rule not found in knowledge scope")
                if len(rows) != 1:
                    raise LookupError("rule identity is ambiguous in knowledge scope")
                rule = self._to_rule(rows[0])
                validate_rule_status_transition(rule.status, target)
                cursor.execute(
                    "UPDATE framework_rule SET status = %s WHERE id = %s",
                    (target.value, rows[0]["id"]),
                )
        return replace(rule, status=target)

    def active_rules_for(
        self,
        prefix: str,
        *,
        scope: KnowledgeScope | None = None,
    ) -> list[FrameworkRule]:
        self._grant.require(Capability.DATABASE_READ)
        if scope is None:
            raise ValueError("PostgreSQL rule retrieval requires an explicit scope")
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT kind, expected_value, confidence, support_count,
                          conflict_count, origin, status, framework_version,
                          discovered_at, evidence_json, metadata_json,
                          customer_id, framework_id, framework_version_id,
                          project_id, module_id
                   FROM framework_rule
                   WHERE status = %s AND kind LIKE %s
                     AND customer_id = %s AND framework_id = %s
                     AND framework_version_id = %s AND project_id = %s
                     AND module_id IS NOT DISTINCT FROM %s
                   ORDER BY confidence DESC, kind, id""",
                ("active", f"{prefix}.%", *scope.hierarchy),
            )
            return [self._to_rule(row) for row in cursor.fetchall()]

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _rule_parameters(rule: FrameworkRule) -> tuple[object, ...]:
        assert rule.scope is not None
        return (
            rule.kind,
            json.dumps(rule.expected_value),
            rule.confidence,
            rule.support_count,
            rule.conflict_count,
            str(rule.origin),
            str(rule.status),
            rule.framework_version,
            rule.discovered_at,
            json.dumps([item.__dict__ for item in rule.evidence]),
            json.dumps(dict(rule.metadata)),
            *rule.scope.hierarchy,
        )

    @staticmethod
    def _to_rule(row: Mapping[str, Any]) -> FrameworkRule:
        scope = KnowledgeScope(
            customer_id=row["customer_id"],
            framework_id=row["framework_id"],
            framework_version_id=row["framework_version_id"],
            project_id=row["project_id"],
            module_id=row["module_id"],
        )
        evidence_data = row["evidence_json"]
        metadata = row["metadata_json"]
        expected_value = row["expected_value"]
        if isinstance(evidence_data, str):
            evidence_data = json.loads(evidence_data)
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if not isinstance(expected_value, str):
            expected_value = json.dumps(expected_value, sort_keys=True)
        discovered_at = row["discovered_at"]
        if isinstance(discovered_at, str):
            discovered_at = datetime.fromisoformat(discovered_at)
        return FrameworkRule(
            kind=row["kind"],
            expected_value=expected_value,
            confidence=row["confidence"],
            support_count=row["support_count"],
            conflict_count=row["conflict_count"],
            evidence=tuple(Evidence(**item) for item in evidence_data),
            metadata=metadata,
            origin=row["origin"],
            status=row["status"],
            framework_version=row["framework_version"],
            discovered_at=discovered_at,
            scope=scope,
        )

    @staticmethod
    def _to_review(row: Mapping[str, Any]) -> RuleReview:
        expected_value = row["expected_value"]
        replacement = row["replacement_json"]
        if not isinstance(expected_value, str):
            expected_value = json.dumps(expected_value, sort_keys=True)
        if isinstance(replacement, str):
            replacement = json.loads(replacement)
        reviewed_at = row["reviewed_at"]
        if isinstance(reviewed_at, str):
            reviewed_at = datetime.fromisoformat(reviewed_at)
        return RuleReview(
            rule_kind=row["rule_kind"], expected_value=expected_value,
            scope=KnowledgeScope(
                row["customer_id"], row["framework_id"], row["framework_version_id"],
                row["project_id"], row["module_id"],
            ),
            action=row["action"], actor=row["actor"], comment=row["comment"],
            replacement=replacement, reviewed_at=reviewed_at,
        )
