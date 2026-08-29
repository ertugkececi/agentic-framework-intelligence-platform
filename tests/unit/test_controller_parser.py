from __future__ import annotations

import pytest

from agentic_platform.tasks.parser import TaskParseError, parse_development_task
from agentic_platform.tasks.types import DevelopmentTask, OperationSpec, ParameterSpec


def test_controller_task_parses_name_only() -> None:
    task = parse_development_task("Create OrderController")
    assert task == DevelopmentTask("controller", "OrderController", ())


def test_controller_task_parses_with_method_and_parameters() -> None:
    task = parse_development_task("Create PaymentController with method handle(account_id, amount)")
    assert task == DevelopmentTask(
        "controller",
        "PaymentController",
        (OperationSpec("handle", (ParameterSpec("account_id"), ParameterSpec("amount"))),),
    )


def test_service_task_still_parses_after_controller_grammar_added() -> None:
    task = parse_development_task("Create CustomerAccountService with method get_account(account_id)")
    assert task == DevelopmentTask(
        "service",
        "CustomerAccountService",
        (OperationSpec("get_account", (ParameterSpec("account_id"),)),),
    )


def test_service_task_without_method_still_parses() -> None:
    task = parse_development_task("Create EmptyService")
    assert task == DevelopmentTask("service", "EmptyService", ())


def test_unknown_artifact_suffix_rejected() -> None:
    with pytest.raises(TaskParseError):
        parse_development_task("Create SomethingBuilder")