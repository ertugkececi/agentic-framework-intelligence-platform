import os
from pathlib import Path
import subprocess
import sys

from agentic_platform.orchestration.graph import run_poc


def test_poc_discovers_retrieves_generates_validates_and_tests(tmp_path: Path) -> None:
    result = run_poc(workspace=tmp_path)

    assert result["status"] == "succeeded"
    assert result["build_result"].passed is True
    assert result["test_result"].passed is True
    assert result["validation_report"].passed is True
    assert result["generated_files"] == ["app/customer_account_service.py"]
    assert result["framework_rules"]
    assert any(rule.expected_value == "BaseService" for rule in result["framework_rules"])
    assert any(rule.kind == "logging.required_call" for rule in result["framework_rules"])

    generated = (tmp_path / "customer-repo" / "app" / "customer_account_service.py").read_text()
    assert "@business_service" in generated
    assert "class CustomerAccountService(BaseService):" in generated
    assert "logger.info" in generated


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
