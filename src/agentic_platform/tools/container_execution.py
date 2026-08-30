"""Capability-enforced container execution for fixed build and test commands."""
from __future__ import annotations

import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentic_platform.domain.models import CommandResult
from agentic_platform.security.policy import Capability, CapabilityGrant, _StagingAuthorization


_DIGEST_PINNED_IMAGE = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}")
_MEMORY_LIMIT = re.compile(r"[1-9][0-9]*[bkmg]", re.IGNORECASE)
_ALLOWED_RUNTIMES = frozenset({"docker", "podman"})
_BUILD_COMMAND = ("python", "-m", "compileall", "-q", "app")
_TEST_COMMAND = ("python", "-m", "pytest", "-q")


@dataclass(frozen=True)
class ContainerExecutionConfig:
    """Immutable, bounded settings for an OCI command runner."""

    image: str
    runtime: str = "docker"
    timeout_seconds: float = 30.0
    max_output_chars: int = 8_000
    cpu_limit: float = 1.0
    memory_limit: str = "512m"
    pids_limit: int = 128

    def __post_init__(self) -> None:
        if not isinstance(self.image, str) or _DIGEST_PINNED_IMAGE.fullmatch(self.image) is None:
            raise ValueError("container image must be pinned by a lowercase sha256 digest")
        if self.runtime not in _ALLOWED_RUNTIMES:
            raise ValueError("container runtime must be docker or podman")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("container timeout must be positive")
        if not isinstance(self.max_output_chars, int) or isinstance(self.max_output_chars, bool) or self.max_output_chars < 1:
            raise ValueError("container output limit must be a positive integer")
        if not isinstance(self.cpu_limit, (int, float)) or isinstance(self.cpu_limit, bool) or not math.isfinite(self.cpu_limit) or self.cpu_limit <= 0:
            raise ValueError("container CPU limit must be positive")
        if not isinstance(self.memory_limit, str) or _MEMORY_LIMIT.fullmatch(self.memory_limit) is None:
            raise ValueError("container memory limit must be a bounded byte value")
        if not isinstance(self.pids_limit, int) or isinstance(self.pids_limit, bool) or self.pids_limit < 1:
            raise ValueError("container PID limit must be a positive integer")


class ContainerCommandRunner:
    """Run only product-defined build and test commands in a locked-down OCI container."""

    def __init__(self, config: ContainerExecutionConfig) -> None:
        if not isinstance(config, ContainerExecutionConfig):
            raise TypeError("config must be ContainerExecutionConfig")
        self._config = config

    def run_build(
        self,
        repository: Path,
        grant: CapabilityGrant,
        *,
        staging_authorization: _StagingAuthorization | None = None,
    ) -> CommandResult:
        self._authorize(Capability.RUN_BUILD, repository, grant, staging_authorization)
        return self._run(repository, _BUILD_COMMAND)

    def run_tests(
        self,
        repository: Path,
        grant: CapabilityGrant,
        *,
        staging_authorization: _StagingAuthorization | None = None,
    ) -> CommandResult:
        self._authorize(Capability.RUN_TEST, repository, grant, staging_authorization)
        return self._run(repository, _TEST_COMMAND)

    @staticmethod
    def _authorize(
        capability: Capability,
        repository: Path,
        grant: CapabilityGrant,
        staging_authorization: _StagingAuthorization | None,
    ) -> None:
        grant.require(capability)
        if staging_authorization is None:
            grant.require_repository(repository)
        else:
            staging_authorization.require_repository(grant, repository)

    def _run(self, repository: Path, fixed_command: tuple[str, ...]) -> CommandResult:
        repository_root = repository.resolve()
        if not repository_root.is_dir():
            raise ValueError("container repository must be a directory")
        if "," in str(repository_root) or "\n" in str(repository_root):
            raise ValueError("container repository path contains unsupported mount characters")
        runtime = shutil.which(self._config.runtime)
        if runtime is None:
            raise RuntimeError(f"container runtime is unavailable: {self._config.runtime}")
        runtime_path = Path(runtime)
        if not runtime_path.is_absolute() or runtime_path.name != self._config.runtime:
            raise RuntimeError("container runtime resolved to an invalid executable")
        command = (
            str(runtime_path), "run", "--rm",
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--cpus", str(self._config.cpu_limit),
            "--memory", self._config.memory_limit,
            "--pids-limit", str(self._config.pids_limit),
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--mount", f"type=bind,src={repository_root},dst=/workspace",
            "--workdir", "/workspace",
            "--entrypoint", fixed_command[0],
            self._config.image,
            *fixed_command[1:],
        )
        try:
            completed = subprocess.run(
                command,
                cwd=repository_root,
                text=True,
                capture_output=True,
                check=False,
                timeout=float(self._config.timeout_seconds),
            )
        except subprocess.TimeoutExpired as error:
            output = self._bounded_output(error.stdout, error.stderr, "\ncommand timed out")
            return CommandResult(False, command, output, timed_out=True)
        except OSError as error:
            return CommandResult(False, command, self._bounded_output(str(error)))
        output = self._bounded_output(completed.stdout, completed.stderr)
        return CommandResult(completed.returncode == 0, command, output)

    def _bounded_output(self, *parts: str | bytes | None) -> str:
        text = "".join(
            part.decode(errors="replace") if isinstance(part, bytes) else (part or "")
            for part in parts
        )
        return text[: self._config.max_output_chars]
