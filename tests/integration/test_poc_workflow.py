import os
from pathlib import Path
import shutil
import subprocess
import sys

from agentic_platform.orchestration.graph import run_development_task, run_poc


def rule_values(result: dict[str, object]) -> dict[str, str]:
    return {
        rule.kind: rule.expected_value
        for rule in result["framework_rules"]  # type: ignore[index,union-attr]
    }


def test_framework_a_is_learned_and_used_to_generate_code(tmp_path: Path) -> None:
    result = run_poc(workspace=tmp_path, sample_name="sample_customer_repo")

    assert result["status"] == "succeeded"
    assert result["build_result"].passed is True
    assert result["test_result"].passed is True
    assert result["validation_report"].passed is True
    assert rule_values(result) == {
        "service.base_class": "BaseService",
        "service.required_decorator": "business_service",
        "logging.logger_class": "CompanyLogger",
        "logging.logger_attribute": "logger",
        "logging.required_method": "info",
    }

    generated = (tmp_path / "customer-repo" / "app" / "customer_account_service.py").read_text()
    assert "from app.framework import BaseService, CompanyLogger, business_service" in generated
    assert "@business_service" in generated
    assert "class CustomerAccountService(BaseService):" in generated
    assert "self.logger = CompanyLogger(__name__)" in generated
    assert "self.logger.info(" in generated


def test_framework_b_is_learned_and_used_without_product_code_change(tmp_path: Path) -> None:
    result = run_poc(workspace=tmp_path, sample_name="sample_customer_repo_b")

    assert result["status"] == "succeeded"
    assert result["build_result"].passed is True
    assert result["test_result"].passed is True
    assert result["validation_report"].passed is True
    assert rule_values(result) == {
        "service.base_class": "FrameworkComponent",
        "service.required_decorator": "managed_component",
        "logging.logger_class": "EnterpriseLog",
        "logging.logger_attribute": "log",
        "logging.required_method": "audit",
    }

    generated = (tmp_path / "customer-repo" / "app" / "customer_account_service.py").read_text()
    assert "from app.enterprise_framework import EnterpriseLog, FrameworkComponent, managed_component" in generated
    assert "@managed_component" in generated
    assert "class CustomerAccountService(FrameworkComponent):" in generated
    assert "self.log = EnterpriseLog(__name__)" in generated
    assert "self.log.audit(" in generated


def test_mutating_customer_framework_symbol_changes_generated_code_without_product_change(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "mutated-customer-repo"
    shutil.copytree(root / "examples" / "sample_customer_repo_b", repository)
    framework_source = repository / "app" / "enterprise_framework.py"
    framework_source.write_text(framework_source.read_text().replace("FrameworkComponent", "DomainUnit"))
    for service in (repository / "app").glob("*_service.py"):
        service.write_text(service.read_text().replace("FrameworkComponent", "DomainUnit"))

    result = run_development_task(workspace=tmp_path, repository=repository)

    assert result["status"] == "succeeded"
    assert rule_values(result)["service.base_class"] == "DomainUnit"
    generated = (repository / "app" / "customer_account_service.py").read_text()
    assert "class CustomerAccountService(DomainUnit):" in generated


def test_product_source_contains_no_customer_framework_symbols() -> None:
    root = Path(__file__).resolve().parents[2]
    forbidden = {
        "BaseService",
        "business_service",
        "CompanyLogger",
        "FrameworkComponent",
        "managed_component",
        "EnterpriseLog",
    }
    product_files = (root / "src" / "agentic_platform").rglob("*.py")
    violations = {
        symbol: path.relative_to(root).as_posix()
        for path in product_files
        for symbol in forbidden
        if symbol in path.read_text(encoding="utf-8")
    }
    assert not violations, f"Customer symbols leaked into product source: {violations}"


def test_unsupported_task_finalizes_without_missing_result_key_error(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    repository = tmp_path / "customer-repo"
    shutil.copytree(root / "examples" / "sample_customer_repo", repository)

    result = run_development_task(workspace=tmp_path, repository=repository, task="Rename README")

    assert result["status"] == "failed"
    assert "task_unsupported" in result["events"]


def test_cli_exits_successfully_after_temporary_workspace_cleanup() -> None:
    project_root = Path(__file__).resolve().parents[2]
    environment = {**os.environ, "PYTHONPATH": "src"}
    completed = subprocess.run(
        [sys.executable, "-m", "agentic_platform.cli"],
        cwd=project_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert '"status": "succeeded"' in completed.stdout
