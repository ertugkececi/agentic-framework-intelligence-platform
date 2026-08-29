from __future__ import annotations

from pathlib import Path

from agentic_platform.domain.models import FrameworkRule, RuleStatus
from agentic_platform.validation.compliance import validate_artifact, validate_service


def test_validate_controller_passes_with_required_structure(tmp_path: Path) -> None:
    rules = [
        FrameworkRule(
            "controller.base_class",
            "BaseController",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "BaseController"},
            status=RuleStatus.ACTIVE,
        ),
        FrameworkRule(
            "controller.required_decorator",
            "controller_decorator",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "controller_decorator"},
            status=RuleStatus.ACTIVE,
        ),
    ]

    source = tmp_path / "generated_controller.py"
    source.write_text(
        "from app.framework import BaseController, controller_decorator\n\n"
        "@controller_decorator\n"
        "class GeneratedController(BaseController):\n"
        "    def __init__(self) -> None:\n"
        "        pass\n",
        encoding="utf-8",
    )

    report = validate_artifact(source, rules, "controller")

    assert report.passed


def test_validate_controller_fails_when_base_class_missing(tmp_path: Path) -> None:
    rules = [
        FrameworkRule(
            "controller.base_class",
            "BaseController",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "BaseController"},
            status=RuleStatus.ACTIVE,
        ),
        FrameworkRule(
            "controller.required_decorator",
            "controller_decorator",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "controller_decorator"},
            status=RuleStatus.ACTIVE,
        ),
    ]

    source = tmp_path / "generated_controller.py"
    source.write_text(
        "from app.framework import controller_decorator\n\n"
        "@controller_decorator\n"
        "class GeneratedController:\n"
        "    def __init__(self) -> None:\n"
        "        pass\n",
        encoding="utf-8",
    )

    report = validate_artifact(source, rules, "controller")

    assert not report.passed
    assert any(finding.rule_kind == "controller.base_class" for finding in report.findings)


def test_validate_controller_fails_when_decorator_missing(tmp_path: Path) -> None:
    rules = [
        FrameworkRule(
            "controller.base_class",
            "BaseController",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "BaseController"},
            status=RuleStatus.ACTIVE,
        ),
        FrameworkRule(
            "controller.required_decorator",
            "controller_decorator",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "controller_decorator"},
            status=RuleStatus.ACTIVE,
        ),
    ]

    source = tmp_path / "generated_controller.py"
    source.write_text(
        "from app.framework import BaseController\n\n"
        "class GeneratedController(BaseController):\n"
        "    def __init__(self) -> None:\n"
        "        pass\n",
        encoding="utf-8",
    )

    report = validate_artifact(source, rules, "controller")

    assert not report.passed
    assert any(finding.rule_kind == "controller.required_decorator" for finding in report.findings)


def test_validate_service_backward_compatible_wrapper(tmp_path: Path) -> None:
    rules = [
        FrameworkRule(
            "service.base_class",
            "BaseService",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "BaseService"},
            status=RuleStatus.ACTIVE,
        ),
        FrameworkRule(
            "service.required_decorator",
            "business_service",
            1.0,
            3,
            0,
            (),
            metadata={"import_module": "app.framework", "import_symbol": "business_service"},
            status=RuleStatus.ACTIVE,
        ),
    ]

    source = tmp_path / "generated_service.py"
    source.write_text(
        "from app.framework import BaseService, business_service\n\n"
        "@business_service\n"
        "class GeneratedService(BaseService):\n"
        "    def __init__(self) -> None:\n"
        "        pass\n",
        encoding="utf-8",
    )

    report = validate_service(source, rules)

    assert report.passed