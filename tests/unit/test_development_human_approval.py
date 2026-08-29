from __future__ import annotations

import shutil
from pathlib import Path

from agentic_platform.agents.development import (
    ChangePlan,
    HumanApprovalDecision,
    HumanApprovalRequest,
)
from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.security.policy import poc_grant


ROOT = Path(__file__).resolve().parents[2]
TASK = "Create ApprovalService with method run()"


def _passing(*args) -> CommandResult:
    return CommandResult(True, ("check",), "passed")


class RequireEveryPlanApproval:
    def requires_approval(self, plan: ChangePlan) -> bool:
        return True


def _service() -> DevelopmentService:
    return DevelopmentService(
        approval_policy_factory=RequireEveryPlanApproval,
        build_runner=_passing,
        test_runner=_passing,
        validator=lambda *args: ValidationReport(True),
    )


def _prepared_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "customer-repo"
    shutil.copytree(ROOT / "examples/sample_customer_repo", repository)
    FrameworkLearningService().learn(tmp_path, repository)
    return repository


def test_development_run_interrupts_before_generation_and_resumes_after_approval(tmp_path: Path) -> None:
    repository = _prepared_repository(tmp_path)
    service = _service()

    pending = service.run(
        tmp_path, repository, TASK, run_id="approval-run-001", grant=poc_grant(repository)
    )

    assert pending["status"] == "needs_human_review"
    assert pending["approval_request"] == HumanApprovalRequest(
        run_id="approval-run-001",
        artifact_family="service",
        artifact_name="ApprovalService",
        target_paths=("app/approval_service.py", "tests/test_approval_service.py"),
        rule_kinds=pending["plan"].rule_kinds,
    )
    assert "change_generated" not in pending["events"]
    assert not (repository / "app/approval_service.py").exists()
    assert Path(pending["staging_repository"]).is_dir()

    result = _service().resume(
        tmp_path,
        repository,
        "approval-run-001",
        HumanApprovalDecision(True, "reviewer@example.test", "bounded plan approved"),
        grant=poc_grant(repository),
    )

    assert result["status"] == "succeeded"
    assert result["approval_decision"].approved
    assert result["events"].index("human_approval_requested") < result["events"].index("human_approval_granted")
    assert result["events"].index("human_approval_granted") < result["events"].index("change_generated")
    assert (repository / "app/approval_service.py").is_file()
    assert not Path(pending["staging_repository"]).exists()


def test_rejected_human_approval_fails_closed_without_generation_or_publish(tmp_path: Path) -> None:
    repository = _prepared_repository(tmp_path)
    service = _service()
    before = {path.relative_to(repository): path.read_bytes() for path in repository.rglob("*") if path.is_file()}
    pending = service.run(
        tmp_path, repository, TASK, run_id="approval-run-002", grant=poc_grant(repository)
    )

    result = _service().resume(
        tmp_path,
        repository,
        "approval-run-002",
        HumanApprovalDecision(False, "reviewer@example.test", "plan is too broad"),
        grant=poc_grant(repository),
    )

    after = {path.relative_to(repository): path.read_bytes() for path in repository.rglob("*") if path.is_file()}
    assert result["status"] == "failed"
    assert "human_approval_rejected" in result["events"]
    assert "change_generated" not in result["events"]
    assert "change_published" not in result["events"]
    assert after == before
    assert not Path(pending["staging_repository"]).exists()
