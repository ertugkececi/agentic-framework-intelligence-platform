from __future__ import annotations

import shutil

import pytest
from pathlib import Path

from agentic_platform.agents.development import (
    ChangePlan, ChangeReview, DeterministicChangeReviewer,
)
from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.security.policy import poc_grant
from agentic_platform.tasks.types import FileChange, GeneratedChange


ROOT = Path(__file__).resolve().parents[2]
TASK = "Create PlannedService with method run()"


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "customer-repo"
    shutil.copytree(ROOT / "examples/sample_customer_repo", repository)
    return repository


def _passing(*args) -> CommandResult:
    return CommandResult(True, ("check",), "passed")


class RecordingPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def plan(
        self, task, context, rules,
    ) -> ChangePlan:
        self.calls += 1
        return ChangePlan(
            artifact_family=task.artifact_type,
            artifact_name=task.artifact_name,
            target_paths=("app/planned_service.py", "tests/test_planned_service.py"),
            rule_kinds=tuple(sorted({rule.kind for rule in rules})),
        )


class RecordingReviewer:
    def __init__(self, approved: bool) -> None:
        self.approved = approved
        self.calls = 0

    def review(self, plan, change, report) -> ChangeReview:
        self.calls += 1
        return ChangeReview(self.approved, "approved" if self.approved else "revision required")


def test_development_graph_plans_before_generation_and_reviews_before_publish(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    planner = RecordingPlanner()
    reviewer = RecordingReviewer(True)

    result = DevelopmentService(
        planner_factory=lambda: planner,
        reviewer_factory=lambda: reviewer,
        build_runner=_passing,
        test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, grant=poc_grant(repository))

    assert result["status"] == "succeeded"
    assert planner.calls == reviewer.calls == 1
    assert result["plan"].artifact_name == "PlannedService"
    assert result["plan"].rule_kinds
    assert result["review"].approved
    assert result["events"].index("change_planned") < result["events"].index("change_generated")
    assert result["events"].index("change_review_approved") < result["events"].index("change_published")


def test_rejected_review_fails_closed_and_keeps_customer_repository_unchanged(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    before = {path.relative_to(repository): path.read_bytes() for path in repository.rglob("*") if path.is_file()}

    result = DevelopmentService(
        planner_factory=RecordingPlanner,
        reviewer_factory=lambda: RecordingReviewer(False),
        build_runner=_passing,
        test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, grant=poc_grant(repository))

    after = {path.relative_to(repository): path.read_bytes() for path in repository.rglob("*") if path.is_file()}
    assert result["status"] == "failed"
    assert result["review"].reason == "revision required"
    assert "change_review_rejected" in result["events"]
    assert "change_published" not in result["events"]
    assert after == before



def test_change_plan_rejects_paths_outside_the_bounded_repository() -> None:
    with pytest.raises(ValueError, match="relative POSIX"):
        ChangePlan("service", "UnsafeService", ("../unsafe.py",))


def test_default_reviewer_rejects_unplanned_generated_paths() -> None:
    plan = ChangePlan("service", "SafeService", ("app/safe_service.py",))
    change = GeneratedChange((FileChange("app/other.py", "VALUE = 1\n"),), "unplanned")

    review = DeterministicChangeReviewer().review(plan, change, ValidationReport(True))

    assert not review.approved
    assert review.reason == "unplanned target paths: app/other.py"


class RepairAwareModel:
    def __init__(self) -> None:
        from agentic_platform.models.gateway import DeterministicPythonCodingModel
        self._delegate = DeterministicPythonCodingModel()
        self.repair_failures = []

    def generate_change(self, task, context):
        return self._delegate.generate_change(task, context)

    def repair_change(self, task, context, previous_change, failure_context):
        self.repair_failures.append(failure_context)
        return self._delegate.repair_change(task, context, previous_change, failure_context)


class RejectOnceReviewer:
    def __init__(self) -> None:
        self.calls = 0

    def review(self, plan, change, report) -> ChangeReview:
        self.calls += 1
        if self.calls == 1:
            return ChangeReview(False, "architecture boundary mismatch")
        return ChangeReview(True, "repair accepted")


def test_rejected_review_enters_bounded_repair_loop_with_review_feedback(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    FrameworkLearningService().learn(tmp_path, repository)
    model = RepairAwareModel()
    reviewer = RejectOnceReviewer()

    result = DevelopmentService(
        model_factory=lambda: model,
        reviewer_factory=lambda: reviewer,
        build_runner=_passing,
        test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    ).run(tmp_path, repository, TASK, retry_budget=1, grant=poc_grant(repository))

    assert result["status"] == "succeeded"
    assert reviewer.calls == 2
    assert result["retry_count"] == 1
    assert len(model.repair_failures) == 1
    assert model.repair_failures[0].stage == "review"
    assert model.repair_failures[0].output == "architecture boundary mismatch"
    assert "review_failed" in result["events"]
    assert result["events"].index("change_review_rejected") < result["events"].index("change_repaired")
    assert result["events"].index("change_repaired") < result["events"].index("change_review_approved")
