from __future__ import annotations

import shutil
from pathlib import Path

from agentic_platform.framework_learning.learner import FrameworkLearner
from agentic_platform.models.gateway import DeterministicPythonCodingModel
import agentic_platform.orchestration.graph as graph
from agentic_platform.orchestration.graph import DevelopmentService, FrameworkLearningService
from agentic_platform.security.policy import poc_grant
from agentic_platform.validation.compliance import validate_service


ROOT = Path(__file__).resolve().parents[2]


def _repository(tmp_path: Path, fixture: str) -> Path:
    repository = tmp_path / "customer-repo"
    shutil.copytree(ROOT / "examples" / fixture, repository)
    return repository


def test_lifecycle_publishes_each_fixture_learned_invocation(tmp_path: Path) -> None:
    for fixture, expected_invocation in (
        ("sample_customer_repo", "self.logger.info('get_account invoked')"),
        ("sample_customer_repo_b", "self.log.audit('get_account invoked')"),
    ):
        workspace = tmp_path / fixture
        repository = _repository(workspace, fixture)
        FrameworkLearningService().learn(workspace, repository)

        result = DevelopmentService().run(
            workspace,
            repository,
            "Create CustomerAccountService with method get_account(account_id)",
            grant=poc_grant(repository),
        )

        generated = (repository / "app/customer_account_service.py").read_text(encoding="utf-8")
        assert result["status"] == "succeeded"
        assert expected_invocation in generated
        dependency = next(item for item in result["coding_context"].dependencies if item.class_name)
        assert dependency.required_invocations
        assert dependency.required_invocations[0].argument_shapes == ("string_literal",)


def test_lifecycle_rejects_generated_source_that_removes_required_invocation(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "sample_customer_repo")
    FrameworkLearningService().learn(tmp_path, repository)

    class InvocationRemovingModel:
        def __init__(self) -> None:
            self.delegate = DeterministicPythonCodingModel()

        def generate_change(self, task, context):
            change = self.delegate.generate_change(task, context)
            source = change.files[0].content.replace("        self.logger.info('get_account invoked')\n", "")
            return type(change)((type(change.files[0])(change.files[0].path, source), *change.files[1:]), change.summary)

        def repair_change(self, task, context, previous_change, failure_context):
            return self.generate_change(task, context)

    result = DevelopmentService(model_factory=InvocationRemovingModel).run(
        tmp_path,
        repository,
        "Create CustomerAccountService with method get_account(account_id)",
        retry_budget=0,
        grant=poc_grant(repository),
    )

    assert result["status"] == "failed"
    assert result["failure_context"].stage == "compliance"
    assert result["validation_report"].findings[0].rule_kind == "dependency.invocation"
    assert "logger.info" in result["validation_report"].findings[0].message
    assert not (repository / "app/customer_account_service.py").exists()


def test_unsupported_required_invocation_fails_before_customer_publish(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "sample_customer_repo")
    for source_path in (repository / "app").glob("*_service.py"):
        source_path.write_text(
            source_path.read_text(encoding="utf-8").replace('self.logger.info("Order created")', "self.logger.info(event)")
            .replace('self.logger.info("Payment received")', "self.logger.info(event)")
            .replace('self.logger.info("Profile updated")', "self.logger.info(event)"),
            encoding="utf-8",
        )
    FrameworkLearningService().learn(tmp_path, repository)

    result = DevelopmentService().run(
        tmp_path,
        repository,
        "Create UnsupportedInvocationService with method run()",
        grant=poc_grant(repository),
    )

    assert result["status"] == "failed"
    assert "required_invocation_unsupported" in result["events"]
    assert not (repository / "app/unsupported_invocation_service.py").exists()


def test_validator_reports_changed_required_invocation_argument_shape(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "sample_customer_repo")
    rules = FrameworkLearner().learn(repository)
    generated = repository / "app/generated_service.py"
    generated.write_text(
        "from app.framework import BaseService, CompanyLogger, business_service\n\n"
        "@business_service\n"
        "class GeneratedService(BaseService):\n"
        "    def __init__(self) -> None:\n"
        "        self.logger = CompanyLogger(__name__)\n\n"
        "    def work(self) -> None:\n"
        "        self.logger.info(1)\n"
        "        return None\n",
        encoding="utf-8",
    )

    report = validate_service(generated, rules)

    assert not report.passed
    assert any(finding.rule_kind == "dependency.invocation" for finding in report.findings)


def test_sparse_invocation_evidence_does_not_become_a_required_call(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "sample_customer_repo")
    (repository / "app/order_service.py").write_text(
        (repository / "app/order_service.py").read_text(encoding="utf-8").replace(
            'self.logger.info("Order created")', "pass"
        ),
        encoding="utf-8",
    )
    (repository / "app/payment_service.py").write_text(
        (repository / "app/payment_service.py").read_text(encoding="utf-8").replace(
            'self.logger.info("Payment received")', "pass"
        ),
        encoding="utf-8",
    )

    rules = FrameworkLearner().learn(repository)
    logger_rule = next(rule for rule in rules if rule.kind == "dependency.constructor" and rule.expected_value == "logger")

    assert logger_rule.status.value == "active"
    assert logger_rule.metadata["required_invocations"] == []


def test_repeated_invocation_evidence_becomes_a_required_call(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "sample_customer_repo")

    rules = FrameworkLearner().learn(repository)
    logger_rule = next(rule for rule in rules if rule.kind == "dependency.constructor" and rule.expected_value == "logger")

    requirement = logger_rule.metadata["required_invocations"]
    assert len(requirement) == 1
    assert requirement[0]["method_name"] == "info"
    assert requirement[0]["argument_shapes"] == ["string_literal"]
    assert requirement[0]["support_count"] == 3
    assert requirement[0]["confidence"] == 1.0


def test_lifecycle_fails_closed_without_an_operation_before_staging_or_publish(tmp_path: Path, monkeypatch) -> None:
    repository = _repository(tmp_path, "sample_customer_repo")
    FrameworkLearningService().learn(tmp_path, repository)
    monkeypatch.setattr(graph.shutil, "copytree", lambda *args: (_ for _ in ()).throw(AssertionError("must not stage")))

    result = DevelopmentService().run(
        tmp_path,
        repository,
        "Create EmptyService",
        grant=poc_grant(repository),
    )

    assert result["status"] == "failed"
    assert "required_invocation_operation_missing" in result["events"]
    assert "change_applied_to_staging" not in result["events"]
    assert not (repository / "app/empty_service.py").exists()


def test_lifecycle_allows_empty_service_when_no_invocation_requirement_is_active(tmp_path: Path) -> None:
    repository = _repository(tmp_path, "sample_customer_repo")
    for source_path in (repository / "app").glob("*_service.py"):
        source_path.write_text(
            source_path.read_text(encoding="utf-8").replace('self.logger.info("Order created")', "pass")
            .replace('self.logger.info("Payment received")', "pass")
            .replace('self.logger.info("Profile updated")', "pass"),
            encoding="utf-8",
        )
    FrameworkLearningService().learn(tmp_path, repository)

    result = DevelopmentService().run(
        tmp_path,
        repository,
        "Create EmptyService",
        grant=poc_grant(repository),
    )

    assert result["status"] == "succeeded"
    assert (repository / "app/empty_service.py").exists()


def test_lifecycle_preserves_import_aliases_from_learning_through_validation(tmp_path: Path) -> None:
    repository = tmp_path / "customer-repo"
    app = repository / "app"
    app.mkdir(parents=True)
    (app / "framework.py").write_text(
        "class BaseService: pass\n"
        "def service(cls): return cls\n"
        "class CompanyLogger:\n"
        "    def __init__(self, name): pass\n"
        "    def info(self, message): pass\n",
        encoding="utf-8",
    )
    for name in ("order", "payment", "profile"):
        (app / f"{name}_service.py").write_text(
            "from app.framework import BaseService as FrameworkBase, CompanyLogger as AuditLog, service as registered\n\n"
            "@registered\n"
            f"class {name.title()}Service(FrameworkBase):\n"
            "    def __init__(self) -> None:\n"
            "        self.logger = AuditLog(__name__)\n\n"
            "    def run(self) -> None:\n"
            "        self.logger.info('recorded')\n",
            encoding="utf-8",
        )
    FrameworkLearningService().learn(tmp_path, repository)

    result = DevelopmentService().run(
        tmp_path,
        repository,
        "Create AliasedService with method run()",
        grant=poc_grant(repository),
    )
    generated = (app / "aliased_service.py").read_text(encoding="utf-8")

    assert result["status"] == "succeeded"
    assert "from app.framework import BaseService as FrameworkBase, CompanyLogger as AuditLog, service as registered" in generated
    assert "@registered" in generated
    assert "class AliasedService(FrameworkBase):" in generated
    assert "self.logger = AuditLog(__name__)" in generated
    assert validate_service(app / "aliased_service.py", result["framework_rules"]).passed
