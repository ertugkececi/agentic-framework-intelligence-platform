"""Checkpoint provider ports for local and production LangGraph runs."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, ContextManager, Iterator, Protocol

from langgraph.checkpoint.sqlite import SqliteSaver


class CheckpointProvider(Protocol):
    """Open durable checkpointers without exposing credentials to graph state."""

    def available(self, workspace: Path) -> bool: ...

    def open(self, workspace: Path) -> ContextManager[Any]: ...


class SqliteCheckpointProvider:
    """Workspace-local checkpoint provider retained for PoC operation."""

    @staticmethod
    def database_path(workspace: Path) -> Path:
        return workspace.resolve() / "development_checkpoints.sqlite"

    def available(self, workspace: Path) -> bool:
        return self.database_path(workspace).is_file()

    @contextmanager
    def open(self, workspace: Path) -> Iterator[Any]:
        path = self.database_path(workspace)
        path.parent.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(str(path)) as checkpointer:
            yield checkpointer


class PostgresCheckpointProvider:
    """Production checkpoint provider backed by PostgresSaver.

    The dependency is imported only when a checkpoint is opened, so local and
    air-gapped PoC paths do not require the production package. The DSN remains
    provider-private and is never inserted into persisted LangGraph state.
    """

    def __init__(self, dsn: str, *, initialize_schema: bool = True) -> None:
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("checkpoint dsn must be a non-empty string")
        if not isinstance(initialize_schema, bool):
            raise TypeError("initialize_schema must be a bool")
        self._dsn = dsn
        self._initialize_schema = initialize_schema

    def available(self, workspace: Path) -> bool:
        return True

    @contextmanager
    def open(self, workspace: Path) -> Iterator[Any]:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise RuntimeError(
                "PostgreSQL checkpoints require langgraph-checkpoint-postgres"
            ) from exc
        with PostgresSaver.from_conn_string(self._dsn) as checkpointer:
            if self._initialize_schema:
                checkpointer.setup()
            yield checkpointer
