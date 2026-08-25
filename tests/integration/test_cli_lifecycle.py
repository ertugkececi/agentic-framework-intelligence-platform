"""Public CLI lifecycle tests executed through real subprocesses."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_REPOSITORY = PROJECT_ROOT / "examples" / "sample_customer_repo"
TASK = "Create CustomerAccountService with method get_account(account_id)"


def run_cli(*arguments: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "agentic_platform.cli", *arguments],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def parse_outcome(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stdout, result.stderr
    return json.loads(result.stdout)


def test_readme_quickstart_run_creates_knowledge_and_generated_artifacts(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repo"
    workspace = tmp_path / "workspace"
    shutil.copytree(SAMPLE_REPOSITORY, repository)

    result = run_cli(
        "run",
        "--repository",
        str(repository),
        "--workspace",
        str(workspace),
        "--task",
        TASK,
        "--deterministic",
    )

    outcome = parse_outcome(result)
    assert result.returncode == 0, result.stderr
    assert outcome["status"] == "succeeded"
    assert outcome["command"] == "run"
    assert Path(outcome["knowledge_database"]).is_file()
    assert (repository / "app/customer_account_service.py").is_file()
    assert (repository / "tests/test_customer_account_service.py").is_file()


def test_learn_then_develop_reuses_persisted_knowledge(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repo"
    workspace = tmp_path / "workspace"
    shutil.copytree(SAMPLE_REPOSITORY, repository)

    learned = run_cli("learn", "--repository", str(repository), "--workspace", str(workspace), "--deterministic")
    developed = run_cli(
        "develop",
        "--repository",
        str(repository),
        "--workspace",
        str(workspace),
        "--task",
        TASK,
        "--deterministic",
    )

    assert learned.returncode == 0, learned.stderr
    assert parse_outcome(learned)["status"] == "succeeded"
    assert developed.returncode == 0, developed.stderr
    assert parse_outcome(developed)["status"] == "succeeded"
    assert (workspace / "framework_knowledge.sqlite").is_file()
    assert (repository / "app/customer_account_service.py").is_file()


def test_develop_rejects_knowledge_learned_from_a_different_repository(tmp_path: Path) -> None:
    learned_repository = tmp_path / "learned-repository"
    target_repository = tmp_path / "target-repository"
    workspace = tmp_path / "workspace"
    shutil.copytree(SAMPLE_REPOSITORY, learned_repository)
    shutil.copytree(SAMPLE_REPOSITORY, target_repository)

    learned = run_cli(
        "learn", "--repository", str(learned_repository), "--workspace", str(workspace), "--deterministic"
    )
    developed = run_cli(
        "develop",
        "--repository",
        str(target_repository),
        "--workspace",
        str(workspace),
        "--task",
        TASK,
        "--deterministic",
    )

    outcome = parse_outcome(developed)
    assert learned.returncode == 0, learned.stderr
    assert developed.returncode != 0
    assert outcome["status"] == "failed"
    assert outcome["error"]["code"] == "framework_knowledge_repository_mismatch"
    assert not (target_repository / "app/customer_account_service.py").exists()
    assert not (target_repository / "tests/test_customer_account_service.py").exists()


def test_develop_without_knowledge_fails_concisely(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repo"
    shutil.copytree(SAMPLE_REPOSITORY, repository)

    result = run_cli(
        "develop",
        "--repository",
        str(repository),
        "--workspace",
        str(tmp_path / "workspace"),
        "--task",
        TASK,
        "--deterministic",
    )

    outcome = parse_outcome(result)
    assert result.returncode != 0
    assert outcome["status"] == "failed"
    assert outcome["error"]["code"] == "framework_knowledge_missing"
    assert "Traceback" not in result.stderr


def test_invalid_repository_and_failed_workflow_have_machine_readable_errors(tmp_path: Path) -> None:
    missing_repository = tmp_path / "missing"
    invalid_repository = run_cli(
        "learn",
        "--repository",
        str(missing_repository),
        "--workspace",
        str(tmp_path / "workspace"),
        "--deterministic",
    )

    repository = tmp_path / "customer-repo"
    shutil.copytree(SAMPLE_REPOSITORY, repository)
    failed_workflow = run_cli(
        "run",
        "--repository",
        str(repository),
        "--workspace",
        str(tmp_path / "failed-workspace"),
        "--task",
        "do something",
        "--deterministic",
    )

    invalid_outcome = parse_outcome(invalid_repository)
    workflow_outcome = parse_outcome(failed_workflow)
    assert invalid_repository.returncode != 0
    assert invalid_outcome["error"]["code"] == "invalid_repository"
    assert failed_workflow.returncode != 0
    assert workflow_outcome["error"]["code"] == "workflow_failed"
    assert "Traceback" not in invalid_repository.stderr + failed_workflow.stderr
