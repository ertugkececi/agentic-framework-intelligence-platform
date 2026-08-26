from __future__ import annotations

import shutil
from pathlib import Path

from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.models.gateway import CodingModelError, DeterministicPythonCodingModel
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.security.policy import poc_grant
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


class FailingCodingModel:
    def __init__(self, *, fail_on: str, secret: str) -> None:
        self.fail_on = fail_on
        self.secret = secret
        self._delegate = DeterministicPythonCodingModel()

    def generate_change(self, task, context) -> GeneratedChange:
        if self.fail_on == "generate":
            raise CodingModelError(f"provider rejected token {self.secret}")
        return self._delegate.generate_change(task, context)

    def repair_change(self, task, context, previous_change, failure_context) -> GeneratedChange:
        if self.fail_on == "repair":
            raise CodingModelError(f"provider rejected token {self.secret}")
        return self._delegate.repair_change(task, context, previous_change, failure_context)


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
    ).run(tmp_path, repository, "Create RetrySuccessService", grant=poc_grant(repository))

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
    ).run(tmp_path, repository, "Create RepairContractService", grant=poc_grant(repository))

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
    ).run(tmp_path, repository, "Create RetryExhaustedService", grant=poc_grant(repository))

    assert result["status"] == "failed"
    assert result["retry_budget"] == 2
    assert result["retry_count"] == 2
    assert build_attempts == 3
    assert model.generate_calls == 1
    assert len(model.repair_calls) == 2
    assert len(result["failure_history"]) == 3
    assert result["failure_context"].attempt == 3
    assert "retry_budget_exhausted" in result["events"]


def test_development_service_records_generation_model_error_without_leaking_error_or_crashing(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)

    result = DevelopmentService(
        model_factory=lambda: FailingCodingModel(fail_on="generate", secret="model-api-secret"),
    ).run(tmp_path, repository, "Create ModelFailureService", grant=poc_grant(repository))

    assert result["status"] == "failed"
    assert result["retry_count"] == 0
    assert result["events"][-1] == "model_generation_failed"
    assert "model-api-secret" not in repr(result)


def test_development_service_records_repair_model_error_without_consuming_budget_or_leaking_error(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)

    result = DevelopmentService(
        model_factory=lambda: FailingCodingModel(fail_on="repair", secret="model-api-secret"),
        build_runner=lambda path, grant: CommandResult(False, ("build",), "syntax error"),
    ).run(tmp_path, repository, "Create RepairModelFailureService", retry_budget=1, grant=poc_grant(repository))

    assert result["status"] == "failed"
    assert result["retry_count"] == 0
    assert "model_repair_failed" in result["events"]
    assert "retry_budget_exhausted" not in result["events"]
    assert "model-api-secret" not in repr(result)


def test_development_service_uses_one_model_instance_for_generation_and_repair(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    models: list[RecordingCodingModel] = []

    def factory() -> RecordingCodingModel:
        model = RecordingCodingModel()
        models.append(model)
        return model

    build_attempts = 0

    def build_then_passes(path: Path, grant: object) -> CommandResult:
        nonlocal build_attempts
        build_attempts += 1
        return CommandResult(build_attempts == 2, ("build",), "broken")

    result = DevelopmentService(
        model_factory=factory,
        build_runner=build_then_passes,
        test_runner=_passing_tests,
        validator=_passing_validation,
    ).run(tmp_path, repository, "Create SharedModelService", grant=poc_grant(repository))

    assert result["status"] == "succeeded"
    assert len(models) == 1
    assert models[0].generate_calls == 1
    assert len(models[0].repair_calls) == 1
