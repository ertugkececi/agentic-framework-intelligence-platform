"""Authoritative structured knowledge store; SQLite is the self-contained PoC adapter."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from agentic_platform.domain.models import Evidence, FrameworkRule


class SQLiteKnowledgeStore:
    def __init__(self, database_path: Path) -> None:
        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS framework_rule (
              id INTEGER PRIMARY KEY, kind TEXT NOT NULL, expected_value TEXT NOT NULL,
              confidence REAL NOT NULL, support_count INTEGER NOT NULL, conflict_count INTEGER NOT NULL,
              origin TEXT NOT NULL, status TEXT NOT NULL, framework_version TEXT NOT NULL,
              discovered_at TEXT NOT NULL, evidence_json TEXT NOT NULL, metadata_json TEXT NOT NULL
            )
        """)
        self.connection.commit()

    def replace_rules(self, rules: list[FrameworkRule]) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM framework_rule")
            self.connection.executemany(
                """INSERT INTO framework_rule
                (kind, expected_value, confidence, support_count, conflict_count, origin, status, framework_version, discovered_at, evidence_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(
                    rule.kind, rule.expected_value, rule.confidence, rule.support_count,
                    rule.conflict_count, str(rule.origin), str(rule.status), rule.framework_version,
                    rule.discovered_at.isoformat(), json.dumps([e.__dict__ for e in rule.evidence]),
                    json.dumps(dict(rule.metadata)),
                ) for rule in rules],
            )

    def active_rules_for(self, prefix: str) -> list[FrameworkRule]:
        rows = self.connection.execute(
            "SELECT * FROM framework_rule WHERE status = 'active' AND kind LIKE ? ORDER BY confidence DESC",
            (f"{prefix}.%",),
        ).fetchall()
        return [self._to_rule(row) for row in rows]

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _to_rule(row: sqlite3.Row) -> FrameworkRule:
        return FrameworkRule(
            kind=row["kind"], expected_value=row["expected_value"], confidence=row["confidence"],
            support_count=row["support_count"], conflict_count=row["conflict_count"],
            origin=row["origin"], status=row["status"], framework_version=row["framework_version"],
            evidence=tuple(Evidence(**item) for item in json.loads(row["evidence_json"])),
            metadata=json.loads(row["metadata_json"]),
        )
