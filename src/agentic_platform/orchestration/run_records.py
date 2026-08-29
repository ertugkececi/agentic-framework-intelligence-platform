"""Immutable, content-addressed development run and artifact records."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath, Path

from agentic_platform.domain.models import FrameworkRule
from agentic_platform.tasks.types import GeneratedChange


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_digest(name: str, value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class DevelopmentArtifactRecord:
    path: str
    content_hash: str
    size: int

    def __post_init__(self) -> None:
        path = PurePosixPath(self.path)
        if not self.path or path.is_absolute() or ".." in path.parts or "\\" in self.path or str(path) != self.path:
            raise ValueError("artifact paths must be normalized relative POSIX paths")
        _require_digest("content_hash", self.content_hash)
        if self.size < 0:
            raise ValueError("artifact size must not be negative")

    @classmethod
    def from_content(cls, path: str, content: str) -> "DevelopmentArtifactRecord":
        encoded = content.encode("utf-8")
        return cls(path, _digest(encoded), len(encoded))


@dataclass(frozen=True)
class DevelopmentRunRecord:
    run_id: str
    repository_revision: str
    task_hash: str
    model_identity: str
    retry_budget: int
    knowledge_rule_ids: tuple[str, ...]
    artifacts: tuple[DevelopmentArtifactRecord, ...]
    status: str

    def __post_init__(self) -> None:
        if not self.run_id.strip() or not self.model_identity.strip():
            raise ValueError("run and model identities must be non-empty")
        _require_digest("repository_revision", self.repository_revision)
        _require_digest("task_hash", self.task_hash)
        if self.retry_budget < 0:
            raise ValueError("retry budget must not be negative")
        if self.status not in {"running", "needs_human_review", "succeeded", "failed"}:
            raise ValueError("invalid development run status")
        if tuple(sorted(set(self.knowledge_rule_ids))) != self.knowledge_rule_ids:
            raise ValueError("knowledge rule identities must be unique and sorted")
        for rule_id in self.knowledge_rule_ids:
            _require_digest("knowledge_rule_id", rule_id)
        paths = tuple(artifact.path for artifact in self.artifacts)
        if len(paths) != len(set(paths)):
            raise ValueError("artifact paths must be unique")

    @property
    def input_identity(self) -> str:
        return _digest(json.dumps({
            "repository_revision": self.repository_revision,
            "task_hash": self.task_hash,
            "model_identity": self.model_identity,
            "retry_budget": self.retry_budget,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8"))

    @property
    def identity(self) -> str:
        return _digest(self.to_json().encode("utf-8"))

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> "DevelopmentRunRecord":
        value = json.loads(payload)
        value["knowledge_rule_ids"] = tuple(value["knowledge_rule_ids"])
        value["artifacts"] = tuple(DevelopmentArtifactRecord(**item) for item in value["artifacts"])
        return cls(**value)

    @classmethod
    def capture(
        cls, *, run_id: str, repository_revision: str, task: str,
        model_identity: str, retry_budget: int, rules: list[FrameworkRule],
        change: GeneratedChange | None, status: str,
    ) -> "DevelopmentRunRecord":
        rule_ids = tuple(sorted({_rule_identity(rule) for rule in rules}))
        artifacts = tuple(
            DevelopmentArtifactRecord.from_content(file.path, file.content)
            for file in (change.files if change is not None else ())
        )
        return cls(
            run_id=run_id, repository_revision=repository_revision,
            task_hash=_digest(task.encode("utf-8")), model_identity=model_identity,
            retry_budget=retry_budget, knowledge_rule_ids=rule_ids,
            artifacts=artifacts, status=status,
        )


def _rule_identity(rule: FrameworkRule) -> str:
    scope = rule.scope.hierarchy if rule.scope is not None else None
    return _digest(json.dumps({
        "kind": rule.kind, "expected_value": rule.expected_value,
        "scope": scope, "framework_version": rule.framework_version,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8"))


class DevelopmentRunRecordStore:
    """SQLite audit adapter with fail-closed run-ID input pinning."""

    def __init__(self, database_path: Path) -> None:
        self.connection = sqlite3.connect(database_path)
        self.connection.execute("""CREATE TABLE IF NOT EXISTS development_run_record (
            run_id TEXT PRIMARY KEY, input_identity TEXT NOT NULL,
            record_identity TEXT NOT NULL, payload_json TEXT NOT NULL
        )""")
        self.connection.commit()

    def save(self, record: DevelopmentRunRecord) -> None:
        with self.connection:
            cursor = self.connection.execute(
                """INSERT INTO development_run_record
                (run_id, input_identity, record_identity, payload_json) VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  record_identity = excluded.record_identity,
                  payload_json = excluded.payload_json
                WHERE development_run_record.input_identity = excluded.input_identity""",
                (record.run_id, record.input_identity, record.identity, record.to_json()),
            )
            if cursor.rowcount != 1:
                raise ValueError("run_id cannot be reused with different inputs")

    def get(self, run_id: str) -> DevelopmentRunRecord | None:
        row = self.connection.execute(
            "SELECT record_identity, payload_json FROM development_run_record WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        record = DevelopmentRunRecord.from_json(row[1])
        if record.identity != row[0]:
            raise ValueError("development run record identity mismatch")
        return record

    def close(self) -> None:
        self.connection.close()
