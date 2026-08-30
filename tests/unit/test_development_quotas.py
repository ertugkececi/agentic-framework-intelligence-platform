from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.models.gateway import DeterministicPythonCodingModel
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.security.policy import poc_grant
from agentic_platform.security.quotas import DevelopmentQuota

SAMPLE = Path(__file__).resolve().parents[2] / "examples" / "sample_customer_repo"
TASK = "Create QuotaBoundaryService with method run()"

def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "customer-repo"
    shutil.copytree(SAMPLE, repository)
    FrameworkLearningService().learn(tmp_path, repository)
    return repository

def _passing(*args: object) -> CommandResult:
    return CommandResult(True, ("fixed",), "passed")

@pytest.mark.parametrize("values", ({"max_duration_seconds": 0}, {"max_model_calls": 0}, {"max_command_executions": 0}, {"max_generated_bytes": 0}, {"max_model_calls": True}))
def test_development_quota_rejects_unbounded_or_invalid_limits(values: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        DevelopmentQuota(**values)

def test_generated_byte_quota_fails_before_staging_apply_or_publish(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    result = DevelopmentService(build_runner=_passing, test_runner=_passing, validator=lambda *args: ValidationReport(True)).run(tmp_path, repository, TASK, grant=poc_grant(repository), quota=DevelopmentQuota(max_generated_bytes=1))
    assert result["status"] == "failed"
    assert result["events"][-1] == "generated_bytes_quota_exhausted"
    assert result["resource_usage"].model_calls == 1
    assert result["resource_usage"].generated_bytes > 1
    assert not (repository / "app" / "quota_boundary_service.py").exists()
    assert "change_applied_to_staging" not in result["events"]

def test_model_call_quota_stops_repair_before_second_model_invocation(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    class CountingModel:
        def __init__(self) -> None:
            self.delegate = DeterministicPythonCodingModel(); self.calls = 0
        def generate_change(self, task, context):
            self.calls += 1; return self.delegate.generate_change(task, context)
        def repair_change(self, task, context, previous_change, failure_context):
            self.calls += 1; return self.delegate.repair_change(task, context, previous_change, failure_context)
    model = CountingModel()
    result = DevelopmentService(model_factory=lambda: model, build_runner=lambda *args: CommandResult(False, ("build",), "broken")).run(tmp_path, repository, TASK, retry_budget=2, grant=poc_grant(repository), quota=DevelopmentQuota(max_model_calls=1))
    assert result["status"] == "failed"
    assert model.calls == 1
    assert result["events"][-1] == "model_calls_quota_exhausted"
    assert result["resource_usage"].command_executions == 1

def test_wall_clock_quota_is_checked_before_model_creation(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    ticks = iter((100.0, 102.0, 102.0, 102.0, 102.0))
    model_created = False
    def model_factory():
        nonlocal model_created
        model_created = True
        return DeterministicPythonCodingModel()
    result = DevelopmentService(model_factory=model_factory, clock=lambda: next(ticks)).run(tmp_path, repository, TASK, grant=poc_grant(repository), quota=DevelopmentQuota(max_duration_seconds=1))
    assert result["status"] == "failed"
    assert result["events"][-1] == "run_time_quota_exhausted"
    assert not model_created


def test_command_quota_stops_before_test_execution(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    test_calls = 0
    def tests(*args: object) -> CommandResult:
        nonlocal test_calls
        test_calls += 1
        return _passing()
    result = DevelopmentService(
        build_runner=_passing,
        test_runner=tests,
        validator=lambda *args: ValidationReport(True),
    ).run(
        tmp_path,
        repository,
        TASK,
        grant=poc_grant(repository),
        quota=DevelopmentQuota(max_command_executions=1),
    )
    assert result["status"] == "failed"
    assert result["events"][-1] == "command_executions_quota_exhausted"
    assert result["resource_usage"].command_executions == 1
    assert test_calls == 0
    assert not (repository / "app" / "quota_boundary_service.py").exists()
