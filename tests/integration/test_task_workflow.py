from pathlib import Path

import pytest

from agentic_platform.orchestration.graph import run_poc
from agentic_platform.tasks.parser import TaskParseError, parse_development_task
from agentic_platform.tasks.types import FileChange, GeneratedChange
from agentic_platform.tools.changes import ChangeValidationError, validate_change


def test_parser_extracts_dynamic_artifact_and_operation() -> None:
    task = parse_development_task("Create PaymentHistoryService with method list_history(customer_id)")
    assert task.artifact_name == "PaymentHistoryService"
    assert task.operations[0].name == "list_history"
    assert task.operations[0].parameters[0].name == "customer_id"


def test_different_tasks_generate_different_artifacts_and_operations(tmp_path: Path) -> None:
    first = run_poc(tmp_path / "first", task="Create CustomerAccountService with method get_account(account_id)")
    second = run_poc(tmp_path / "second", task="Create PaymentHistoryService with method list_history(customer_id)")
    assert "class CustomerAccountService" in (tmp_path / "first/customer-repo/app/customer_account_service.py").read_text()
    output = (tmp_path / "second/customer-repo/app/payment_history_service.py").read_text()
    assert "class PaymentHistoryService" in output and "def list_history" in output
    assert first["status"] == second["status"] == "succeeded"


def test_invalid_or_unsafe_generated_change_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ChangeValidationError):
        validate_change(GeneratedChange((FileChange("../escape.py", "x"),), "bad"), tmp_path)
    with pytest.raises(TaskParseError):
        parse_development_task("do something")
