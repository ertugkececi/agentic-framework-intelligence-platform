"""Capability-enforced generated-change validation and application."""
from __future__ import annotations

from pathlib import Path

from agentic_platform.security.policy import Capability, CapabilityGrant
from agentic_platform.tasks.types import GeneratedChange


class ChangeValidationError(ValueError):
    """Raised when a generated change violates the repository write policy."""


ALLOWED_ROOTS = ("app", "tests")
PROTECTED_NAMES = {".git", ".env", "secrets", "credentials"}


def validate_change(change: GeneratedChange, repository: Path) -> None:
    """Reject unsafe, duplicate, or empty model-proposed changes before writes."""
    paths: set[str] = set()
    root = repository.resolve()
    for file_change in change.files:
        relative_path = Path(file_change.path)
        target = (root / relative_path).resolve()
        if not file_change.content or relative_path.is_absolute() or file_change.path in paths:
            raise ChangeValidationError(file_change.path)
        if root not in target.parents or not relative_path.parts or relative_path.parts[0] not in ALLOWED_ROOTS:
            raise ChangeValidationError(file_change.path)
        if any(part in PROTECTED_NAMES or part.startswith(".env") for part in relative_path.parts):
            raise ChangeValidationError(file_change.path)
        paths.add(file_change.path)


def apply_change(change: GeneratedChange, repository: Path, grant: CapabilityGrant) -> list[str]:
    """Apply a validated change only after the repository-write capability check."""
    grant.require(Capability.WRITE_REPOSITORY)
    validate_change(change, repository)
    for file_change in change.files:
        target = repository / file_change.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file_change.content, encoding="utf-8")
    return [file_change.path for file_change in change.files]
