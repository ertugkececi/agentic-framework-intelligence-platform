"""Policy-enforced deterministic build/test tooling."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from agentic_platform.domain.models import CommandResult
from agentic_platform.security.policy import Capability, CapabilityGrant


def run_build(repository: Path, grant: CapabilityGrant) -> CommandResult:
    grant.require(Capability.RUN_BUILD)
    command = (sys.executable, "-m", "compileall", "-q", "app")
    completed = subprocess.run(command, cwd=repository, text=True, capture_output=True, check=False)
    return CommandResult(completed.returncode == 0, command, completed.stdout + completed.stderr)


def run_tests(repository: Path, grant: CapabilityGrant) -> CommandResult:
    grant.require(Capability.RUN_TEST)
    command = (sys.executable, "-m", "pytest", "-q")
    completed = subprocess.run(command, cwd=repository, text=True, capture_output=True, check=False)
    return CommandResult(completed.returncode == 0, command, completed.stdout + completed.stderr)
