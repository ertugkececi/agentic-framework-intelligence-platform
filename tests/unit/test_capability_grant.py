from pathlib import Path

import pytest

from agentic_platform.security.policy import Capability, CapabilityGrant, local_principal


def test_grant_snapshots_mutable_capabilities_and_canonicalizes_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    capabilities = {Capability.READ_REPOSITORY}

    grant = CapabilityGrant(capabilities, repository / ".." / "repository", local_principal("local"))
    capabilities.add(Capability.WRITE_REPOSITORY)

    assert grant.allowed == frozenset({Capability.READ_REPOSITORY})
    assert grant.repository_root == repository.resolve()
    grant.require(Capability.READ_REPOSITORY)
    with pytest.raises(PermissionError, match="write_repository"):
        grant.require(Capability.WRITE_REPOSITORY)


def test_grant_rejects_untyped_capabilities(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="Capability"):
        CapabilityGrant(frozenset({"read_repository"}), tmp_path, local_principal("local"))
