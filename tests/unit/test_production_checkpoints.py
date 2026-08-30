from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import sys
from types import ModuleType

from langgraph.checkpoint.sqlite import SqliteSaver
import pytest

from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.orchestration.checkpoints import PostgresCheckpointProvider
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.security.policy import poc_grant


class RecordingCheckpointProvider:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.opened: list[Path] = []

    def available(self, workspace: Path) -> bool:
        return self.database.is_file()

    @contextmanager
    def open(self, workspace: Path):
        self.opened.append(workspace)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with SqliteSaver.from_conn_string(str(self.database)) as saver:
            yield saver


def test_development_service_uses_injected_checkpoint_provider(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "examples/sample_customer_repo", repository
    )
    workspace = tmp_path / "workspace"
    FrameworkLearningService().learn(workspace, repository)
    provider = RecordingCheckpointProvider(tmp_path / "checkpoint-db" / "state.sqlite")

    result = DevelopmentService(
        checkpoint_provider=provider,
        build_runner=lambda *_: CommandResult(True, ("build",), "ok"),
        test_runner=lambda *_: CommandResult(True, ("test",), "ok"),
        validator=lambda *_: ValidationReport(True),
    ).run(workspace, repository, "Create InvoiceService with method run()", grant=poc_grant(repository))

    assert result["status"] == "succeeded"
    assert provider.opened == [workspace]
    assert provider.database.is_file()
    assert not DevelopmentService.checkpoint_database_path(workspace).exists()


def test_postgres_provider_opens_and_initializes_saver(monkeypatch, tmp_path: Path) -> None:
    calls: list[object] = []

    class FakeSaver:
        def setup(self) -> None:
            calls.append("setup")

    class SaverFactory:
        @staticmethod
        @contextmanager
        def from_conn_string(dsn: str):
            calls.append(dsn)
            yield FakeSaver()

    module = ModuleType("langgraph.checkpoint.postgres")
    module.PostgresSaver = SaverFactory
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.postgres", module)
    provider = PostgresCheckpointProvider("postgresql://platform@postgres/platform")

    assert provider.available(tmp_path) is True
    with provider.open(tmp_path) as saver:
        assert isinstance(saver, FakeSaver)

    assert calls == ["postgresql://platform@postgres/platform", "setup"]


def test_postgres_provider_rejects_blank_dsn() -> None:
    try:
        PostgresCheckpointProvider("  ")
    except ValueError as error:
        assert "dsn" in str(error)
    else:
        raise AssertionError("blank DSN must fail closed")


def test_api_composes_postgres_checkpoint_provider(monkeypatch) -> None:
    import importlib

    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://platform@postgres/platform")
    sys.modules.pop("agentic_platform.api", None)
    api = importlib.import_module("agentic_platform.api")

    assert isinstance(api.CHECKPOINT_PROVIDER, PostgresCheckpointProvider)


def test_api_fails_closed_without_checkpoint_dsn(monkeypatch) -> None:
    import importlib

    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    sys.modules.pop("agentic_platform.api", None)
    with pytest.raises(RuntimeError, match="POSTGRES_DSN"):
        importlib.import_module("agentic_platform.api")
