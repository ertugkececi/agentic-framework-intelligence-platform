from pathlib import Path

import pytest

from agentic_platform.domain.models import KnowledgeScope
from agentic_platform.security.policy import (
    Capability,
    CapabilityGrant,
    Principal,
    Role,
)


def principal(tenant_id: str = "tenant-a", *roles: Role) -> Principal:
    return Principal("user-123", tenant_id, frozenset(roles or (Role.DEVELOPER,)))


def test_principal_and_grant_snapshot_rbac_inputs(tmp_path: Path) -> None:
    roles = {Role.DEVELOPER}
    identity = Principal("user-123", "tenant-a", roles)
    requested = {Capability.READ_REPOSITORY}

    grant = CapabilityGrant(requested, tmp_path, identity)
    roles.add(Role.PLATFORM_ADMIN)
    requested.add(Capability.GIT_PUSH)

    assert identity.roles == frozenset({Role.DEVELOPER})
    assert grant.allowed == frozenset({Capability.READ_REPOSITORY})
    with pytest.raises(PermissionError, match="git_push"):
        grant.require(Capability.GIT_PUSH)


def test_grant_rejects_capabilities_not_authorized_by_roles(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="RBAC denied"):
        CapabilityGrant(
            frozenset({Capability.DATABASE_WRITE}),
            tmp_path,
            principal("tenant-a"),
        )


def test_grant_enforces_tenant_scope(tmp_path: Path) -> None:
    grant = CapabilityGrant(
        frozenset({Capability.DATABASE_READ}),
        tmp_path,
        principal("tenant-a", Role.KNOWLEDGE_ADMIN),
    )
    matching = KnowledgeScope("tenant-a", "framework", "v1", "project")
    other = KnowledgeScope("tenant-b", "framework", "v1", "project")

    grant.require_scope(matching)
    with pytest.raises(PermissionError, match="tenant mismatch"):
        grant.require_scope(other)


def test_identity_values_and_roles_are_strictly_typed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="subject_id"):
        Principal(" ", "tenant-a", frozenset({Role.DEVELOPER}))
    with pytest.raises(ValueError, match="tenant_id"):
        Principal("user-123", "", frozenset({Role.DEVELOPER}))
    with pytest.raises(TypeError, match="Role"):
        Principal("user-123", "tenant-a", frozenset({"developer"}))
    with pytest.raises(TypeError, match="Principal"):
        CapabilityGrant(frozenset(), tmp_path, None)
