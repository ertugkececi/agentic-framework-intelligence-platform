from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from agentic_platform.domain.models import CodingContext, FrameworkRule, ValidationReport
from agentic_platform.tasks.types import DevelopmentTask, GeneratedChange


def _validate_target_path(value: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or str(path) != value:
        raise ValueError("target paths must be normalized relative POSIX paths")


@dataclass(frozen=True)
class ChangePlan:
    artifact_family: str
    artifact_name: str
    target_paths: tuple[str, ...]
    rule_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.artifact_family.strip() or not self.artifact_name.strip():
            raise ValueError("artifact family and name must be non-empty")
        if not self.target_paths or len(set(self.target_paths)) != len(self.target_paths):
            raise ValueError("target paths must be non-empty and unique")
        for path in self.target_paths:
            _validate_target_path(path)


@dataclass(frozen=True)
class HumanApprovalRequest:
    run_id: str
    artifact_family: str
    artifact_name: str
    target_paths: tuple[str, ...]
    rule_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value.strip() for value in (
            self.run_id, self.artifact_family, self.artifact_name,
        )):
            raise ValueError("approval request identity must be non-empty")
        if not self.target_paths:
            raise ValueError("approval request requires target paths")
        for path in self.target_paths:
            _validate_target_path(path)


@dataclass(frozen=True)
class HumanApprovalDecision:
    approved: bool
    actor: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.approved, bool):
            raise ValueError("approval decision must be boolean")
        if not all(isinstance(value, str) and value.strip() for value in (self.actor, self.reason)):
            raise ValueError("approval actor and reason must be non-empty")
        if len(self.actor) > 256 or len(self.reason) > 1_000:
            raise ValueError("approval actor or reason exceeds its bounded size")


@dataclass(frozen=True)
class ChangeReview:
    approved: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.approved, bool) or not self.reason.strip():
            raise ValueError("review requires a boolean decision and non-empty reason")


class ChangePlanner(Protocol):
    def plan(
        self, task: DevelopmentTask, context: CodingContext, rules: tuple[FrameworkRule, ...],
    ) -> ChangePlan: ...


class ChangeReviewer(Protocol):
    def review(self, plan: ChangePlan, change: GeneratedChange, report: ValidationReport) -> ChangeReview: ...


class HumanApprovalPolicy(Protocol):
    def requires_approval(self, plan: ChangePlan) -> bool: ...


class NoHumanApprovalRequired:
    def requires_approval(self, plan: ChangePlan) -> bool:
        return False


class DeterministicChangePlanner:
    def plan(
        self, task: DevelopmentTask, context: CodingContext, rules: tuple[FrameworkRule, ...],
    ) -> ChangePlan:
        if task.artifact_type != context.structure.artifact_family:
            raise ValueError("task and coding context artifact families differ")
        filename = self._snake_case(task.artifact_name)
        return ChangePlan(
            artifact_family=task.artifact_type,
            artifact_name=task.artifact_name,
            target_paths=(f"app/{filename}.py", f"tests/test_{filename}.py"),
            rule_kinds=tuple(sorted({rule.kind for rule in rules})),
        )

    @staticmethod
    def _snake_case(value: str) -> str:
        return "".join(
            f"_{character.lower()}" if character.isupper() else character
            for character in value
        ).lstrip("_")


class DeterministicChangeReviewer:
    def review(self, plan: ChangePlan, change: GeneratedChange, report: ValidationReport) -> ChangeReview:
        proposed = tuple(item.path for item in change.files)
        unplanned = sorted(set(proposed) - set(plan.target_paths))
        if not report.passed:
            return ChangeReview(False, "deterministic validation did not pass")
        if unplanned:
            return ChangeReview(False, "unplanned target paths: " + ", ".join(unplanned))
        return ChangeReview(True, "verified change matches the bounded plan")
