from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.security.policy import poc_grant


ROOT = Path(__file__).resolve().parents[2]
TASK = "Create CheckpointedService with method run()"


def _passing(*args) -> CommandResult:
    return CommandResult(True, ("check",), "passed")


def test_development_run_persists_langgraph_checkpoints_by_run_id(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repo"
    shutil.copytree(ROOT / "examples/sample_customer_repo", repository)
    FrameworkLearningService().learn(tmp_path, repository)

    result = DevelopmentService(
        build_runner=_passing,
        test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(
        tmp_path, repository, TASK, run_id="run-checkpoint-001", grant=poc_grant(repository)
    )

    database = tmp_path / "development_checkpoints.sqlite"
    assert result["status"] == "succeeded"
    assert result["run_id"] == "run-checkpoint-001"
    assert database.is_file()
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoints WHERE thread_id = ?",
            ("run-checkpoint-001",),
        ).fetchall()
    assert len(rows) >= 2
    assert {row[0] for row in rows} == {"run-checkpoint-001"}
