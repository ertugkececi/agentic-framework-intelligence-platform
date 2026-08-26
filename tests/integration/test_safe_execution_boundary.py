from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from agentic_platform.domain.models import CommandResult, ValidationFinding, ValidationReport
import agentic_platform.orchestration.graph as graph
from agentic_platform.framework_learning.learner import FrameworkLearner
from agentic_platform.models.gateway import FailureContext
import agentic_platform.models.openai_compatible as openai_compatible
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
import agentic_platform.security.policy as policy
from agentic_platform.security.policy import Capability, CapabilityGrant, _create_staging_authorization
from agentic_platform.tasks.types import FileChange, GeneratedChange
from agentic_platform.tools.changes import ChangeValidationError, apply_change
from agentic_platform.tools.repository_tools import run_build, run_tests


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "examples" / "sample_customer_repo"
TASK = "Create SafeBoundaryService"


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "customer-repo"
    shutil.copytree(SAMPLE, repository)
    return repository


def _hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _grant(repository: Path, *capabilities: Capability) -> CapabilityGrant:
    return CapabilityGrant(frozenset(capabilities), repository.resolve())


def _full_grant(repository: Path) -> CapabilityGrant:
    return _grant(
        repository,
        Capability.READ_REPOSITORY,
        Capability.WRITE_REPOSITORY,
        Capability.RUN_BUILD,
        Capability.RUN_TEST,
        Capability.STATIC_ANALYSIS,
    )


class ChangeModel:
    def __init__(self, change: GeneratedChange) -> None:
        self.change = change
        self.repair_failures: list[FailureContext] = []

    def generate_change(self, task, context) -> GeneratedChange:
        return self.change

    def repair_change(self, task, context, previous_change, failure_context) -> GeneratedChange:
        self.repair_failures.append(failure_context)
        return self.change


def _change(name: str = "safe_boundary_service") -> GeneratedChange:
    return GeneratedChange((FileChange(f"app/{name}.py", "VALUE = 'generated'\n"),), "generated")


def _passing(*args) -> CommandResult:
    return CommandResult(True, ("fixed",), "passed")


def test_failed_build_keeps_customer_tree_byte_identical(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    before = _hashes(repository)
    result = DevelopmentService(
        model_factory=lambda: ChangeModel(_change()),
        build_runner=lambda *args: CommandResult(False, ("build",), "ordinary failure"),
        test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, grant=_full_grant(repository), retry_budget=0)

    assert result["status"] == "failed"
    assert _hashes(repository) == before
    assert not list((tmp_path / ".development-staging").glob("*"))


def test_failed_tests_keep_customer_tree_byte_identical(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    before = _hashes(repository)
    result = DevelopmentService(
        model_factory=lambda: ChangeModel(_change()), build_runner=_passing,
        test_runner=lambda *args: CommandResult(False, ("pytest",), "test failure"),
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, grant=_full_grant(repository), retry_budget=0)

    assert result["status"] == "failed"
    assert _hashes(repository) == before


def test_failed_compliance_keeps_customer_tree_byte_identical(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    before = _hashes(repository)
    result = DevelopmentService(
        model_factory=lambda: ChangeModel(_change()), build_runner=_passing, test_runner=_passing,
        validator=lambda *args: ValidationReport(False),
    ).run(tmp_path, repository, TASK, grant=_full_grant(repository), retry_budget=0)

    assert result["status"] == "failed"
    assert _hashes(repository) == before


def test_success_publishes_only_new_generated_files(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    before = _hashes(repository)
    result = DevelopmentService(
        model_factory=lambda: ChangeModel(_change()), build_runner=_passing, test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, grant=_full_grant(repository))

    assert result["status"] == "succeeded"
    assert result["generated_files"] == ["app/safe_boundary_service.py"]
    after = _hashes(repository)
    assert set(after) - set(before) == {str(Path("app/safe_boundary_service.py"))}
    assert {key: after[key] for key in before} == before
    assert (repository / "app/safe_boundary_service.py").read_text(encoding="utf-8") == "VALUE = 'generated'\n"


def test_default_model_path_does_not_instantiate_remote_transport(tmp_path: Path, monkeypatch) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    transport_instances = 0

    def unexpected_transport(*args, **kwargs) -> None:
        nonlocal transport_instances
        transport_instances += 1
        raise AssertionError("the deterministic default must not construct remote transport")

    monkeypatch.setattr(openai_compatible.UrllibHttpTransport, "__init__", unexpected_transport)
    result = DevelopmentService(
        build_runner=_passing,
        test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, grant=_full_grant(repository))

    assert result["status"] == "succeeded"
    assert transport_instances == 0


def test_publish_rejects_existing_customer_file_without_overwrite(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    target = repository / "app/existing.py"
    target.write_text("original\n", encoding="utf-8")
    with __import__("pytest").raises(ChangeValidationError):
        apply_change(_change("existing"), repository, _full_grant(repository))
    assert target.read_text(encoding="utf-8") == "original\n"


def test_direct_apply_to_unrelated_repository_is_rejected_before_creating_file(tmp_path: Path) -> None:
    authorized_repository = _repository(tmp_path / "authorized")
    unrelated_repository = _repository(tmp_path / "unrelated")

    with pytest.raises(PermissionError, match="repository mismatch"):
        apply_change(_change(), unrelated_repository, _full_grant(authorized_repository))

    assert not (unrelated_repository / "app" / "safe_boundary_service.py").exists()


@pytest.mark.parametrize("runner", (run_build, run_tests))
def test_direct_command_tools_reject_an_unrelated_repository_root(tmp_path: Path, runner) -> None:
    authorized_repository = _repository(tmp_path / "authorized")
    unrelated_repository = _repository(tmp_path / "unrelated")

    with pytest.raises(PermissionError, match="repository mismatch"):
        runner(unrelated_repository, _full_grant(authorized_repository))


def test_unregistered_staging_path_cannot_mint_authorization(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "authorized")
    stage = tmp_path / ".development-staging" / "generated-run"
    shutil.copytree(repository, stage)

    with pytest.raises(PermissionError, match="Unregistered staging repository"):
        _create_staging_authorization(_full_grant(repository), repository, stage)


def test_staging_authorization_is_factory_issued_and_revoked_after_lifecycle_cleanup(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path / "authorized")
    FrameworkLearningService().learn(tmp_path, repository)
    arbitrary_stage = tmp_path / ".development-staging" / "arbitrary-run"
    shutil.copytree(repository, arbitrary_stage)
    grant = _full_grant(repository)

    with pytest.raises(TypeError):
        policy._StagingAuthorization(repository.resolve(), arbitrary_stage.resolve())
    fabricated = object.__new__(policy._StagingAuthorization)
    for tool in (apply_change, run_build, run_tests):
        with pytest.raises(PermissionError):
            if tool is apply_change:
                tool(_change(), arbitrary_stage, grant, allow_overwrite=True, staging_authorization=fabricated)
            else:
                tool(arbitrary_stage, grant, staging_authorization=fabricated)
    with pytest.raises(PermissionError):
        _create_staging_authorization(grant, repository, arbitrary_stage)

    result = DevelopmentService(
        model_factory=lambda: ChangeModel(_change()), build_runner=_passing, test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, grant=grant)

    assert result["status"] == "succeeded"
    staged_authorization = result["staging_authorization"]
    staged_path = Path(result["staging_repository"])
    assert not staged_path.exists()
    for tool in (apply_change, run_build, run_tests):
        with pytest.raises(PermissionError):
            if tool is apply_change:
                tool(_change("after_cleanup"), staged_path, grant, allow_overwrite=True, staging_authorization=staged_authorization)
            else:
                tool(staged_path, grant, staging_authorization=staged_authorization)


def test_canonical_repository_path_remains_authorized_for_direct_apply(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    assert apply_change(_change(), repository / ".", _full_grant(repository)) == ["app/safe_boundary_service.py"]
    assert (repository / "app" / "safe_boundary_service.py").is_file()


@pytest.mark.parametrize(
    "missing_capability",
    (
        Capability.READ_REPOSITORY,
        Capability.WRITE_REPOSITORY,
        Capability.RUN_BUILD,
        Capability.RUN_TEST,
        Capability.STATIC_ANALYSIS,
    ),
)
def test_each_missing_required_capability_fails_before_model_staging_commands_or_target_writes(
    tmp_path: Path,
    monkeypatch,
    missing_capability: Capability,
) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    before = _hashes(repository)
    model_factory_calls = 0
    build_calls = 0
    test_calls = 0
    staging_attempted = False

    def model_factory() -> ChangeModel:
        nonlocal model_factory_calls
        model_factory_calls += 1
        return ChangeModel(_change())

    def build_runner(*args) -> CommandResult:
        nonlocal build_calls
        build_calls += 1
        return _passing()

    def test_runner(*args) -> CommandResult:
        nonlocal test_calls
        test_calls += 1
        return _passing()

    def unexpected_learning(*args, **kwargs) -> None:
        raise AssertionError("development must not invoke learning")

    def unexpected_staging(*args, **kwargs) -> None:
        nonlocal staging_attempted
        staging_attempted = True
        raise AssertionError("development must not create staging with an incomplete grant")

    monkeypatch.setattr(FrameworkLearningService, "learn", unexpected_learning)
    monkeypatch.setattr(graph.shutil, "copytree", unexpected_staging)
    capabilities = set(_full_grant(repository).allowed)
    capabilities.remove(missing_capability)
    result = DevelopmentService(
        model_factory=model_factory,
        build_runner=build_runner,
        test_runner=test_runner,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, grant=_grant(repository, *capabilities))

    assert result == {
        "repository": str(repository.resolve()),
        "task": TASK,
        "status": "failed",
        "events": ["capability_denied"],
    }
    assert model_factory_calls == build_calls == test_calls == 0
    assert not staging_attempted
    assert _hashes(repository) == before


def test_mismatched_grant_prevents_model_and_side_effects(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    before = _hashes(repository)
    model = ChangeModel(_change())

    result = DevelopmentService(model_factory=lambda: model).run(
        tmp_path,
        repository,
        TASK,
        grant=_full_grant(tmp_path / "other"),
    )

    assert result["status"] == "failed"
    assert model.repair_failures == []
    assert _hashes(repository) == before
    assert result["events"] == ["capability_repository_mismatch"]


def test_no_grant_fails_closed_before_learning_model_staging_or_target_writes(tmp_path: Path, monkeypatch) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    before = _hashes(repository)
    model_factory_calls = 0
    build_calls = 0
    test_calls = 0
    staging_attempted = False

    def model_factory():
        nonlocal model_factory_calls
        model_factory_calls += 1
        return ChangeModel(_change())

    def build_runner(*args) -> CommandResult:
        nonlocal build_calls
        build_calls += 1
        return _passing()

    def test_runner(*args) -> CommandResult:
        nonlocal test_calls
        test_calls += 1
        return _passing()

    def unexpected_learning(*args, **kwargs):
        raise AssertionError("development must not invoke learning")

    def unexpected_staging(*args, **kwargs):
        nonlocal staging_attempted
        staging_attempted = True
        raise AssertionError("development must not create staging without a grant")

    monkeypatch.setattr(FrameworkLearningService, "learn", unexpected_learning)
    monkeypatch.setattr(graph.shutil, "copytree", unexpected_staging)

    result = DevelopmentService(
        model_factory=model_factory,
        build_runner=build_runner,
        test_runner=test_runner,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK)

    assert result["status"] == "failed"
    assert result["events"] == ["capability_grant_required"]
    assert model_factory_calls == build_calls == test_calls == 0
    assert not staging_attempted
    assert _hashes(repository) == before


def test_command_timeout_and_output_capture_are_bounded(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (repository / "app" / "slow.py").write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    result = run_build(repository, _full_grant(repository), timeout_seconds=0.01, max_output_chars=17)
    assert not result.passed
    assert result.timed_out
    assert len(result.output) <= 17


def test_compliance_secret_is_redacted_from_returned_state(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    secret = "TOKEN=not-for-state"
    result = DevelopmentService(
        model_factory=lambda: ChangeModel(_change()), build_runner=_passing, test_runner=_passing,
        validator=lambda *args: ValidationReport(False, (ValidationFinding("rule", secret),)),
    ).run(tmp_path, repository, TASK, grant=_full_grant(repository), retry_budget=0)

    assert secret not in repr(result)
    assert result["validation_report"].findings[0].message == "TOKEN=[REDACTED]"


def test_secret_failure_output_is_redacted_from_state_and_repair_prompt(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    model = ChangeModel(_change())
    secret = "API_KEY=super-secret Bearer abc.def.ghi https://alice:pw@example.test"
    result = DevelopmentService(
        model_factory=lambda: model,
        build_runner=lambda *args: CommandResult(False, ("build",), secret),
        test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, grant=_full_grant(repository), retry_budget=1)

    assert secret not in repr(result)
    assert "[REDACTED]" in result["failure_context"].output
    assert model.repair_failures and secret not in model.repair_failures[0].output


@pytest.mark.parametrize(
    ("secret", "expected"),
    (
        ("API_KEY: colon-form-secret", "API_KEY: [REDACTED]"),
        ('{"api_key": "json-form-secret"}', '{"api_key": "[REDACTED]"}'),
    ),
    ids=("colon_assignment", "json_assignment"),
)
def test_colon_and_json_secret_failures_are_redacted_before_state_and_repair_model(
    tmp_path: Path,
    secret: str,
    expected: str,
) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    model = ChangeModel(_change())
    output = f"Compile error in app/service.py:42: {secret}; expected expression"

    result = DevelopmentService(
        model_factory=lambda: model,
        build_runner=lambda *args: CommandResult(False, ("build",), output),
        test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, grant=_full_grant(repository), retry_budget=1)

    assert secret not in repr(result)
    assert secret not in result["build_result"].output
    assert result["failure_context"].output == f"Compile error in app/service.py:42: {expected}; expected expression"
    assert len(model.repair_failures) == 1
    assert secret not in repr(model.repair_failures[0])
    assert model.repair_failures[0].output == result["failure_context"].output
