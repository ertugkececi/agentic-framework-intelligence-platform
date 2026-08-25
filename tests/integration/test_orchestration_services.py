from __future__ import annotations

import shutil
from pathlib import Path

from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.models.gateway import DeterministicPythonCodingModel
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.tasks.types import GeneratedChange


def _repository(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "examples" / "sample_customer_repo"
    repository = tmp_path / "customer-repo"
    shutil.copytree(source, repository)
    return repository


def _passing_tests(repository: Path, grant: object) -> CommandResult:
    return CommandResult(True, ("test",), "passed")


def _passing_validation(path: Path, rules: list[object]) -> ValidationReport:
    return ValidationReport(True)


class RecordingCodingModel:
    """Keeps repair inputs observable while using real deterministic source generation."""

    def __init__(self) -> None:
        self._delegate = DeterministicPythonCodingModel()
        self.generate_calls = 0
        self.repair_calls: list[tuple[GeneratedChange, object]] = []

    def generate_change(self, task, context) -> GeneratedChange:
        self.generate_calls += 1
        return self._delegate.generate_change(task, context)

    def repair_change(self, task, context, previous_change: GeneratedChange, failure_context: object) -> GeneratedChange:
        self.repair_calls.append((previous_change, failure_context))
        change = self._delegate.generate_change(task, context)
        return GeneratedChange(change.files, f"Repair {len(self.repair_calls)}: {change.summary}")


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


def test_development_service_repairs_the_previous_change_with_failure_context(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    model = RecordingCodingModel()
    build_attempts = 0

    def build_then_passes(path: Path, grant: object) -> CommandResult:
        nonlocal build_attempts
        build_attempts += 1
        return CommandResult(build_attempts == 2, ("build",), "syntax error" if build_attempts == 1 else "passed")

    result = DevelopmentService(
        model_factory=lambda: model,
        build_runner=build_then_passes,
        test_runner=_passing_tests,
        validator=_passing_validation,
    ).run(tmp_path, repository, "Create RepairContractService")

    assert result["status"] == "succeeded"
    assert model.generate_calls == 1
    assert len(model.repair_calls) == 1
    previous_change, failure = model.repair_calls[0]
    assert previous_change.summary == "Create RepairContractService"
    assert failure.stage == "build"
    assert failure.output == "syntax error"
    assert result["generated_change"].summary.startswith("Repair 1:")


def test_development_service_stops_after_default_retry_budget_is_exhausted(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    build_attempts = 0

    def always_fails(path: Path, grant: object) -> CommandResult:
        nonlocal build_attempts
        build_attempts += 1
        return CommandResult(False, ("build",), "still broken")

    model = RecordingCodingModel()
    result = DevelopmentService(
        model_factory=lambda: model,
        build_runner=always_fails,
        test_runner=_passing_tests,
        validator=_passing_validation,
    ).run(tmp_path, repository, "Create RetryExhaustedService")

    assert result["status"] == "failed"
    assert result["retry_budget"] == 2
    assert result["retry_count"] == 2
    assert build_attempts == 3
    assert model.generate_calls == 1
    assert len(model.repair_calls) == 2
    assert len(result["failure_history"]) == 3
    assert result["failure_context"].attempt == 3
    assert "retry_budget_exhausted" in result["events"]
