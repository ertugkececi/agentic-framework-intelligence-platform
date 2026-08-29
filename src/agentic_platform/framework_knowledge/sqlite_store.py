"""Authoritative structured knowledge store; SQLite is the self-contained PoC adapter."""
from __future__ import annotations

import json
import hashlib
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

from agentic_platform.domain.models import Evidence, FrameworkRule, KnowledgeScope


def repository_fingerprint(repository: Path) -> str:
    """Return a stable local-repository identity without storing its path."""
    canonical_path = os.path.normcase(str(repository.resolve()))
    return hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()


class SQLiteKnowledgeStore:
    def __init__(self, database_path: Path) -> None:
        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS framework_rule (
              id INTEGER PRIMARY KEY, kind TEXT NOT NULL, expected_value TEXT NOT NULL,
              confidence REAL NOT NULL, support_count INTEGER NOT NULL, conflict_count INTEGER NOT NULL,
              origin TEXT NOT NULL, status TEXT NOT NULL, framework_version TEXT NOT NULL,
              discovered_at TEXT NOT NULL, evidence_json TEXT NOT NULL, metadata_json TEXT NOT NULL,
              customer_id TEXT, framework_id TEXT, framework_version_id TEXT,
              project_id TEXT, module_id TEXT
            )
        """)
        existing_columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(framework_rule)")
        }
        for column in ("customer_id", "framework_id", "framework_version_id", "project_id", "module_id"):
            if column not in existing_columns:
                self.connection.execute(f"ALTER TABLE framework_rule ADD COLUMN {column} TEXT")
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS framework_knowledge_metadata (
              id INTEGER PRIMARY KEY CHECK (id = 1), repository_fingerprint TEXT NOT NULL
            )
        """)
        self.connection.commit()

    def replace_rules(
        self,
        rules: list[FrameworkRule],
        repository_identity: str | None = None,
        *,
        scope: KnowledgeScope | None = None,
    ) -> None:
        scoped_rules: list[FrameworkRule] = []
        for rule in rules:
            if scope is None and rule.scope is not None:
                raise ValueError("scoped rule writes require an explicit scope")
            if scope is not None and rule.scope is not None and rule.scope != scope:
                raise ValueError("rule scope does not match replacement scope")
            scoped_rules.append(replace(rule, scope=scope) if scope is not None else rule)

        with self.connection:
            if scope is None:
                self.connection.execute(
                    "DELETE FROM framework_rule WHERE customer_id IS NULL AND framework_id IS NULL "
                    "AND framework_version_id IS NULL AND project_id IS NULL AND module_id IS NULL"
                )
            else:
                self.connection.execute(
                    """DELETE FROM framework_rule
                    WHERE customer_id = ? AND framework_id = ? AND framework_version_id = ?
                      AND project_id = ? AND module_id IS ?""",
                    scope.hierarchy,
                )
            if repository_identity is not None:
                self.connection.execute(
                    "INSERT OR REPLACE INTO framework_knowledge_metadata (id, repository_fingerprint) VALUES (1, ?)",
                    (repository_identity,),
                )
            self.connection.executemany(
                """INSERT INTO framework_rule
                (kind, expected_value, confidence, support_count, conflict_count, origin, status,
                 framework_version, discovered_at, evidence_json, metadata_json, customer_id,
                 framework_id, framework_version_id, project_id, module_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(
                    rule.kind, rule.expected_value, rule.confidence, rule.support_count,
                    rule.conflict_count, str(rule.origin), str(rule.status), rule.framework_version,
                    rule.discovered_at.isoformat(), json.dumps([e.__dict__ for e in rule.evidence]),
                    json.dumps(dict(rule.metadata)),
                    *(rule.scope.hierarchy if rule.scope is not None else (None,) * 5),
                ) for rule in scoped_rules],
            )

    def repository_fingerprint(self) -> str | None:
        row = self.connection.execute(
            "SELECT repository_fingerprint FROM framework_knowledge_metadata WHERE id = 1"
        ).fetchone()
        return row["repository_fingerprint"] if row else None

    def active_rules_for(
        self,
        prefix: str,
        *,
        scope: KnowledgeScope | None = None,
    ) -> list[FrameworkRule]:
        if scope is None:
            rows = self.connection.execute(
                """SELECT * FROM framework_rule
                WHERE status = ? AND kind LIKE ?
                  AND customer_id IS NULL AND framework_id IS NULL
                  AND framework_version_id IS NULL AND project_id IS NULL AND module_id IS NULL
                ORDER BY confidence DESC""",
                ("active", f"{prefix}.%"),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """SELECT * FROM framework_rule
                WHERE status = ? AND kind LIKE ?
                  AND customer_id = ? AND framework_id = ? AND framework_version_id = ?
                  AND project_id = ? AND module_id IS ?
                ORDER BY confidence DESC""",
                ("active", f"{prefix}.%", *scope.hierarchy),
            ).fetchall()
        return [self._to_rule(row) for row in rows]

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _to_rule(row: sqlite3.Row) -> FrameworkRule:
        scope = None
        if row["customer_id"] is not None:
            scope = KnowledgeScope(
                customer_id=row["customer_id"],
                framework_id=row["framework_id"],
                framework_version_id=row["framework_version_id"],
                project_id=row["project_id"],
                module_id=row["module_id"],
            )
        return FrameworkRule(
            kind=row["kind"], expected_value=row["expected_value"], confidence=row["confidence"],
            support_count=row["support_count"], conflict_count=row["conflict_count"],
            origin=row["origin"], status=row["status"], framework_version=row["framework_version"],
            evidence=tuple(Evidence(**item) for item in json.loads(row["evidence_json"])),
            metadata=json.loads(row["metadata_json"]), scope=scope,
        )
