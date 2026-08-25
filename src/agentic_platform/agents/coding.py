"""Legacy agent adapter kept intentionally framework- and task-neutral."""
from __future__ import annotations

from pathlib import Path

from agentic_platform.security.policy import CapabilityGrant
from agentic_platform.tasks.types import GeneratedChange
from agentic_platform.tools.changes import apply_change


def apply_generated_change(
    repository: Path,
    change: GeneratedChange,
    grant: CapabilityGrant,
) -> list[str]:
    """Delegate generated-change application to the policy-enforced tool layer."""
    return apply_change(change, repository, grant)
