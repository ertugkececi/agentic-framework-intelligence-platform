"""Policy-enforced deterministic build/test tooling."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from agentic_platform.domain.models import CommandResult
from agentic_platform.security.policy import Capability, CapabilityGrant, _StagingAuthorization

DEFAULT_COMMAND_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_COMMAND_OUTPUT = 8_000


def _require_repository(
    grant: CapabilityGrant, repository: Path, staging_authorization: _StagingAuthorization | None,
) -> None:
    if staging_authorization is None:
        grant.require_repository(repository)
    else:
        staging_authorization.require_repository(grant, repository)


def _run_fixed_command(
    command: tuple[str, ...],
    repository: Path,
    *,
    timeout_seconds: float,
    max_output_chars: int,
) -> CommandResult:
    if timeout_seconds <= 0 or max_output_chars < 1:
        raise ValueError("timeout_seconds and max_output_chars must be positive")
    try:
        completed = subprocess.run(
            command, cwd=repository, text=True, capture_output=True, check=False, timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        output = ((error.stdout or "") + (error.stderr or "") + "\ncommand timed out")[:max_output_chars]
        return CommandResult(False, command, output, timed_out=True)
    output = (completed.stdout + completed.stderr)[:max_output_chars]
    return CommandResult(completed.returncode == 0, command, output)


def run_build(
    repository: Path,
    grant: CapabilityGrant,
    *,
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    max_output_chars: int = DEFAULT_MAX_COMMAND_OUTPUT,
    staging_authorization: _StagingAuthorization | None = None,
) -> CommandResult:
    grant.require(Capability.RUN_BUILD)
    _require_repository(grant, repository, staging_authorization)
    return _run_fixed_command((sys.executable, "-m", "compileall", "-q", "app"), repository, timeout_seconds=timeout_seconds, max_output_chars=max_output_chars)


def run_tests(
    repository: Path,
    grant: CapabilityGrant,
    *,
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    max_output_chars: int = DEFAULT_MAX_COMMAND_OUTPUT,
    staging_authorization: _StagingAuthorization | None = None,
) -> CommandResult:
    grant.require(Capability.RUN_TEST)
    _require_repository(grant, repository, staging_authorization)
    return _run_fixed_command((sys.executable, "-m", "pytest", "-q"), repository, timeout_seconds=timeout_seconds, max_output_chars=max_output_chars)
