from __future__ import annotations

from pathlib import Path

from agentic_platform.domain.models import CommandResult, ValidationReport
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.security.policy import poc_grant


def _passing_validation(path: Path, rules: list[object]) -> ValidationReport:
    return ValidationReport(True)


def test_development_service_retrieves_controller_context_for_controller_task(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "customer-repo"
    import shutil
    shutil.copytree(root / "examples/sample_customer_repo", repository)
    FrameworkLearningService().learn(tmp_path, repository)

    passed = CommandResult(True, ("check",), "passed")
    result = DevelopmentService(
        build_runner=lambda path, grant: passed,
        test_runner=lambda path, grant: passed,
        validator=_passing_validation,
    ).run(tmp_path, repository, "Create OrderController", grant=poc_grant(repository))

    assert result["status"] == "succeeded"
    assert result["coding_context"].structure.artifact_family == "controller"
    assert "BaseService" in result["coding_context"].structure.base_classes
    assert "business_service" in result["coding_context"].structure.decorators


def test_development_service_rejects_controller_when_rules_missing(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "customer-repo"
    import shutil
    shutil.copytree(root / "examples/sample_customer_repo", repository)
    # Learn only service rules by emptying controller observations
    # We learn from repo but controller rules need sufficient evidence
    # Use a repo that has no controllers
    service_only_repo = tmp_path / "service-only"
    service_only_repo.mkdir()
    (service_only_repo / "app").mkdir(parents=True)
    (service_only_repo / "app" / "framework.py").write_text(
        "class BaseService: pass\ndef business_service(cls): return cls\nclass CompanyLogger:\n    def __init__(self, name): pass\n    def info(self, message): pass\n"
    )
    for name in ("order", "payment", "profile"):
        (service_only_repo / "app" / f"{name}_service.py").write_text(
            "from app.framework import BaseService, CompanyLogger, business_service\n"
            f"@business_service\nclass {name.title()}Service(BaseService):\n"
            "    def __init__(self):\n        self.logger = CompanyLogger(__name__)\n"
            "    def run(self):\n        self.logger.info('x')\n"
        )

    FrameworkLearningService().learn(tmp_path, service_only_repo)

    passed = CommandResult(True, ("check",), "passed")
    result = DevelopmentService(
        build_runner=lambda path, grant: passed,
        test_runner=lambda path, grant: passed,
        validator=_passing_validation,
    ).run(tmp_path, service_only_repo, "Create OrderController", grant=poc_grant(service_only_repo))

    assert result["status"] == "failed"
    assert "framework_knowledge_missing" in result["events"]