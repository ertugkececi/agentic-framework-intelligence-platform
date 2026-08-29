"""Capability checks for every tool invocation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import RLock


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
    """Immutable permissions bound to one canonical customer repository root."""

    allowed: frozenset[Capability]
    repository_root: Path

    def __post_init__(self) -> None:
        if not isinstance(self.repository_root, Path):
            raise TypeError("repository_root must be a Path")
        if not all(isinstance(capability, Capability) for capability in self.allowed):
            raise TypeError("allowed entries must be Capability values")
        object.__setattr__(self, "allowed", frozenset(self.allowed))
        object.__setattr__(self, "repository_root", self.repository_root.resolve())

    def require(self, capability: Capability) -> None:
        if capability not in self.allowed:
            raise PermissionError(f"Capability denied: {capability}")

    def require_repository(self, repository: Path) -> None:
        if self.repository_root != repository.resolve():
            raise PermissionError("Capability grant repository mismatch")


@dataclass(frozen=True)
class _StagingRecord:
    """Private registry data for an active service-owned staging lifecycle."""

    workspace_root: Path
    repository_root: Path
    staging_root: Path


class _StagingLifecycle:
    """Unconstructible marker proving the service registered a staging copy."""

    __slots__ = ()

    def __new__(cls, *args: object, **kwargs: object) -> _StagingLifecycle:
        raise TypeError("staging lifecycles are service-issued")


class _StagingAuthorization:
    """Opaque typed-tool capability; authority lives only in the private registry.

    This is an in-process API boundary, not cryptographic protection against
    arbitrary code that deliberately imports and mutates this module's private
    globals.
    """

    __slots__ = ()

    def __new__(cls, *args: object, **kwargs: object) -> _StagingAuthorization:
        raise TypeError("staging authorization is factory-issued")

    def require_repository(self, grant: CapabilityGrant, repository: Path) -> None:
        with _STAGING_REGISTRY_LOCK:
            issuance = _ISSUED_STAGING_AUTHORIZATIONS.get(self)
        if issuance is None:
            raise PermissionError("Unissued staging authorization")
        _, record = issuance
        grant.require_repository(record.repository_root)
        if record.staging_root != repository.resolve():
            raise PermissionError("Capability grant staging repository mismatch")
        if not record.staging_root.is_dir() or record.staging_root.parent != record.workspace_root / ".development-staging":
            raise PermissionError("Inactive staging repository")


# A token's object identity, rather than caller-supplied path fields, is the
# authority. These registries deliberately remain module-private: they enforce
# normal typed tool API capability semantics inside this process.

_STAGING_REGISTRY_LOCK = RLock()
_STAGING_LIFECYCLES: dict[_StagingLifecycle, _StagingRecord] = {}
_ISSUED_STAGING_AUTHORIZATIONS: dict[_StagingAuthorization, tuple[_StagingLifecycle, _StagingRecord]] = {}


def _register_staging_copy(workspace: Path, repository: Path, staging_repository: Path) -> _StagingLifecycle:
    """Register the exact staging copy immediately after service-controlled copytree."""
    workspace_root = workspace.resolve()
    repository_root = repository.resolve()
    staging_root = staging_repository.resolve()
    if not staging_root.is_dir() or staging_root.parent != workspace_root / ".development-staging":
        raise PermissionError("Invalid service staging repository")
    lifecycle = object.__new__(_StagingLifecycle)
    with _STAGING_REGISTRY_LOCK:
        _STAGING_LIFECYCLES[lifecycle] = _StagingRecord(workspace_root, repository_root, staging_root)
    return lifecycle


def _create_staging_authorization(
    grant: CapabilityGrant,
    repository: Path,
    staging_repository: Path,
    lifecycle: _StagingLifecycle | None = None,
) -> _StagingAuthorization:
    """Mint authority only for the exact staging copy registered by the service."""
    repository_root = repository.resolve()
    staging_root = staging_repository.resolve()
    with _STAGING_REGISTRY_LOCK:
        record = _STAGING_LIFECYCLES.get(lifecycle) if lifecycle is not None else None
        if record is None or record.repository_root != repository_root or record.staging_root != staging_root:
            raise PermissionError("Unregistered staging repository")
        grant.require_repository(record.repository_root)
        authorization = object.__new__(_StagingAuthorization)
        _ISSUED_STAGING_AUTHORIZATIONS[authorization] = (lifecycle, record)
    return authorization


def _revoke_staging_authorization(authorization: _StagingAuthorization | None) -> None:
    """Invalidate a token once its disposable staging lifecycle has ended."""
    if authorization is None:
        return
    with _STAGING_REGISTRY_LOCK:
        issuance = _ISSUED_STAGING_AUTHORIZATIONS.pop(authorization, None)
        if issuance is not None:
            lifecycle, _ = issuance
            _STAGING_LIFECYCLES.pop(lifecycle, None)


def poc_grant(repository: Path) -> CapabilityGrant:
    """Create the explicit local-demo grant; no shell, commit, push, or DB write."""
    return CapabilityGrant(
        frozenset({
            Capability.READ_REPOSITORY,
            Capability.WRITE_REPOSITORY,
            Capability.RUN_BUILD,
            Capability.RUN_TEST,
            Capability.STATIC_ANALYSIS,
        }),
        repository.resolve(),
    )
