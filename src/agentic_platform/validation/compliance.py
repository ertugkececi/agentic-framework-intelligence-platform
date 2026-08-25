"""Deterministic AST-based framework compliance checks driven by rules."""
from __future__ import annotations

import ast
from pathlib import Path

from agentic_platform.domain.models import FrameworkRule, ValidationFinding, ValidationReport


def validate_service(source_path: Path, rules: list[FrameworkRule]) -> ValidationReport:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    findings: list[ValidationFinding] = []
    values = {rule.kind: rule.expected_value for rule in rules}
    service = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith("Service")), None)
    if service is None:
        return ValidationReport(False, (ValidationFinding("service.class", "No service class found"),))
    bases = {name for name in (_name(base) for base in service.bases) if name}
    decorators = {name for name in (_name(item) for item in service.decorator_list) if name}
    _expect(values, "service.base_class", bases, findings, "Required base class missing")
    _expect(values, "service.required_decorator", decorators, findings, "Required decorator missing")
    _validate_dependency(service, values, findings)
    _validate_forbidden_calls(service, values, findings)
    return ValidationReport(passed=not findings, findings=tuple(findings))


def _validate_dependency(service: ast.ClassDef, values: dict[str, str], findings: list[ValidationFinding]) -> None:
    attribute = values.get("logging.logger_attribute")
    dependency = values.get("logging.logger_class")
    method = values.get("logging.required_method")
    assignments = {
        target.attr: _name(node.value.func)
        for node in ast.walk(service)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
        for target in node.targets
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self"
    }
    if attribute and assignments.get(attribute) != dependency:
        findings.append(ValidationFinding("logging.logger_class", "Required dependency type/attribute missing"))
    calls = {
        node.func.attr
        for node in ast.walk(service)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute) and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "self" and node.func.value.attr == attribute
    }
    if method and method not in calls:
        findings.append(ValidationFinding("logging.required_method", "Required dependency method call missing"))


def _validate_forbidden_calls(service: ast.ClassDef, values: dict[str, str], findings: list[ValidationFinding]) -> None:
    forbidden = values.get("logging.forbidden_call")
    if not forbidden:
        return
    for node in ast.walk(service):
        if isinstance(node, ast.Call) and _name(node.func) == forbidden:
            findings.append(ValidationFinding("logging.forbidden_call", f"Forbidden call used: {forbidden}"))


def _expect(values: dict[str, str], rule: str, observed: set[str], findings: list[ValidationFinding], message: str) -> None:
    expected = values.get(rule)
    if expected and expected not in observed:
        findings.append(ValidationFinding(rule, message))


def _name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
