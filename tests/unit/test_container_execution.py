from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.security.policy import Capability, CapabilityGrant, _StagingAuthorization
from agentic_platform.tools.container_execution import ContainerExecutionConfig, ContainerCommandRunner


IMAGE = "registry.example.invalid/platform/python@sha256:" + "a" * 64


def _grant(repository: Path, *capabilities: Capability) -> CapabilityGrant:
    return CapabilityGrant(frozenset(capabilities), repository)


def test_build_runs_as_a_fixed_networkless_resource_bounded_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr("agentic_platform.tools.container_execution.shutil.which", lambda runtime: "/usr/bin/docker")

    def completed(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs["cwd"] == repository
        assert kwargs["timeout"] == 12.0
        return subprocess.CompletedProcess(command, 0, "compiled\n", "")

    monkeypatch.setattr("agentic_platform.tools.container_execution.subprocess.run", completed)
    runner = ContainerCommandRunner(
        ContainerExecutionConfig(
            image=IMAGE, runtime="docker", timeout_seconds=12, max_output_chars=100,
            cpu_limit=0.5, memory_limit="256m", pids_limit=64,
        )
    )

    result = runner.run_build(repository, _grant(repository, Capability.RUN_BUILD))

    assert result.passed and result.output == "compiled\n"
    assert calls == [result.command]
    command = result.command
    assert command[0:3] == ("/usr/bin/docker", "run", "--rm")
    assert ("--network", "none") == command[command.index("--network"):command.index("--network") + 2]
    assert "--read-only" in command
    assert ("--cap-drop", "ALL") == command[command.index("--cap-drop"):command.index("--cap-drop") + 2]
    assert ("--security-opt", "no-new-privileges") == command[command.index("--security-opt"):command.index("--security-opt") + 2]
    assert ("--cpus", "0.5") == command[command.index("--cpus"):command.index("--cpus") + 2]
    assert ("--memory", "256m") == command[command.index("--memory"):command.index("--memory") + 2]
    assert ("--pids-limit", "64") == command[command.index("--pids-limit"):command.index("--pids-limit") + 2]
    assert ("--mount", f"type=bind,src={repository.resolve()},dst=/workspace") == command[command.index("--mount"):command.index("--mount") + 2]
    assert command[-7:] == ("--entrypoint", "python", IMAGE, "-m", "compileall", "-q", "app")


def test_tests_use_fixed_pytest_command_and_bound_timeout_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.setattr("agentic_platform.tools.container_execution.shutil.which", lambda runtime: "/usr/bin/podman")

    def timed_out(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="x" * 30, stderr="secret-tail")

    monkeypatch.setattr("agentic_platform.tools.container_execution.subprocess.run", timed_out)
    runner = ContainerCommandRunner(
        ContainerExecutionConfig(image=IMAGE, runtime="podman", timeout_seconds=1, max_output_chars=17)
    )

    result = runner.run_tests(repository, _grant(repository, Capability.RUN_TEST))

    assert not result.passed and result.timed_out
    assert len(result.output) == 17
    assert result.command[-6:] == ("--entrypoint", "python", IMAGE, "-m", "pytest", "-q")


def test_denied_or_mismatched_grant_fails_before_runtime_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    lookups = 0

    def unexpected_lookup(runtime: str) -> str:
        nonlocal lookups
        lookups += 1
        return "/usr/bin/docker"

    monkeypatch.setattr("agentic_platform.tools.container_execution.shutil.which", unexpected_lookup)
    runner = ContainerCommandRunner(ContainerExecutionConfig(image=IMAGE))

    with pytest.raises(PermissionError, match="Capability denied"):
        runner.run_build(repository, _grant(repository))
    with pytest.raises(PermissionError, match="repository mismatch"):
        runner.run_tests(repository, _grant(tmp_path / "other", Capability.RUN_TEST))

    assert lookups == 0


@pytest.mark.parametrize(
    "overrides",
    (
        {"image": "python:latest"},
        {"image": "python@sha256:not-a-digest"},
        {"image": IMAGE, "runtime": "sh"},
        {"image": IMAGE, "cpu_limit": 0},
        {"image": IMAGE, "cpu_limit": float("inf")},
        {"image": IMAGE, "timeout_seconds": float("nan")},
        {"image": IMAGE, "memory_limit": "unlimited"},
        {"image": IMAGE, "pids_limit": 0},
    ),
)
def test_container_configuration_rejects_unpinned_or_unbounded_values(overrides: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        ContainerExecutionConfig(**overrides)


def test_staging_authorization_must_be_genuine_before_runtime_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    stage = tmp_path / "stage"
    repository.mkdir()
    stage.mkdir()
    looked_up = False

    def unexpected_lookup(runtime: str) -> str:
        nonlocal looked_up
        looked_up = True
        return "/usr/bin/docker"

    monkeypatch.setattr("agentic_platform.tools.container_execution.shutil.which", unexpected_lookup)
    runner = ContainerCommandRunner(ContainerExecutionConfig(image=IMAGE))
    fabricated = object.__new__(_StagingAuthorization)

    with pytest.raises(PermissionError, match="Unissued"):
        runner.run_build(
            stage, _grant(repository, Capability.RUN_BUILD), staging_authorization=fabricated,
        )

    assert not looked_up



def test_development_service_uses_container_runner_inside_registered_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = Path(__file__).resolve().parents[2] / "examples" / "sample_customer_repo"
    repository = tmp_path / "customer-repository"
    shutil.copytree(sample, repository)
    FrameworkLearningService().learn(tmp_path, repository)
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr("agentic_platform.tools.container_execution.shutil.which", lambda runtime: "/usr/bin/docker")

    def completed(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "passed\n", "")

    monkeypatch.setattr("agentic_platform.tools.container_execution.subprocess.run", completed)
    runner = ContainerCommandRunner(ContainerExecutionConfig(image=IMAGE))
    grant = _grant(
        repository,
        Capability.READ_REPOSITORY,
        Capability.WRITE_REPOSITORY,
        Capability.RUN_BUILD,
        Capability.RUN_TEST,
        Capability.STATIC_ANALYSIS,
    )

    result = DevelopmentService(container_runner=runner).run(
        tmp_path, repository, "Create ContainerizedService with method run()", grant=grant,
    )

    assert result["status"] == "succeeded"
    calls = [command for command in calls if command[:2] == ("/usr/bin/docker", "run")]
    assert len(calls) == 2
    assert calls[0][-7:] == ("--entrypoint", "python", IMAGE, "-m", "compileall", "-q", "app")
    assert calls[1][-6:] == ("--entrypoint", "python", IMAGE, "-m", "pytest", "-q")
    assert all("/.development-staging/" in command[command.index("--mount") + 1] for command in calls)
    assert not Path(result["staging_repository"]).exists()
