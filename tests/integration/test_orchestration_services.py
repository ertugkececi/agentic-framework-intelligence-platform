from __future__ import annotations

import shutil
from pathlib import Path

from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService


def _repository(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "examples" / "sample_customer_repo"
    repository = tmp_path / "customer-repo"
    shutil.copytree(source, repository)
    return repository


def _passing_tests(repository: Path, grant: object) -> CommandResult:
    return CommandResult(True, ("test",), "passed")


def _passing_validation(path: Path, rules: list[object]) -> ValidationReport:
    return ValidationReport(True)


def test_development_service_retries_a_failed_build_with_bounded_failure_context(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    build_attempts = 0

    def build_then_passes(path: Path, grant: object) -> CommandResult:
        nonlocal build_attempts
        build_attempts += 1
        if build_attempts == 1:
            return CommandResult(False, ("build",), "compiler output: " + "x" * 5_000)
        return CommandResult(True, ("build",), "passed")

    result = DevelopmentService(
        build_runner=build_then_passes,
        test_runner=_passing_tests,
        validator=_passing_validation,
        max_failure_output=120,
    ).run(tmp_path, repository, "Create RetrySuccessService")

    assert result["status"] == "succeeded"
    assert build_attempts == 2
    assert result["retry_count"] == 1
    assert result["failure_context"].stage == "build"
    assert len(result["failure_context"].output) <= 120
    assert result["failure_history"] == (result["failure_context"],)


def test_development_service_stops_after_default_retry_budget_is_exhausted(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    build_attempts = 0

    def always_fails(path: Path, grant: object) -> CommandResult:
        nonlocal build_attempts
        build_attempts += 1
        return CommandResult(False, ("build",), "still broken")

    result = DevelopmentService(
        build_runner=always_fails,
        test_runner=_passing_tests,
        validator=_passing_validation,
    ).run(tmp_path, repository, "Create RetryExhaustedService")

    assert result["status"] == "failed"
    assert result["retry_budget"] == 2
    assert result["retry_count"] == 2
    assert build_attempts == 3
    assert len(result["failure_history"]) == 3
    assert result["failure_context"].attempt == 3
    assert "retry_budget_exhausted" in result["events"]
