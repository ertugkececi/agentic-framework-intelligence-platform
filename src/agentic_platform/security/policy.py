"""Capability checks for every tool invocation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Capability(StrEnum):
    READ_REPOSITORY = "read_repository"
    WRITE_REPOSITORY = "write_repository"
    RUN_BUILD = "run_build"
    RUN_TEST = "run_test"
    STATIC_ANALYSIS = "static_analysis"
    DATABASE_READ = "database_read"
    DATABASE_WRITE = "database_write"
    SHELL_COMMAND = "shell_command"
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"


@dataclass(frozen=True)
class CapabilityGrant:
    allowed: frozenset[Capability]

    def require(self, capability: Capability) -> None:
        if capability not in self.allowed:
            raise PermissionError(f"Capability denied: {capability}")


def poc_grant() -> CapabilityGrant:
    """Least privilege: no arbitrary shell, commit, push, or DB write."""
    return CapabilityGrant(frozenset({
        Capability.READ_REPOSITORY,
        Capability.WRITE_REPOSITORY,
        Capability.RUN_BUILD,
        Capability.RUN_TEST,
        Capability.STATIC_ANALYSIS,
    }))
