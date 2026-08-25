"""Deterministic source-level framework compliance checks."""
from __future__ import annotations

import ast
from pathlib import Path

from agentic_platform.domain.models import FrameworkRule, ValidationFinding, ValidationReport


def validate_service(source_path: Path, rules: list[FrameworkRule]) -> ValidationReport:
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))
    findings: list[ValidationFinding] = []
    service = next((n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name.endswith("Service")), None)
    rule_values = {rule.kind: rule.expected_value for rule in rules}
    if service is None:
        findings.append(ValidationFinding("service.class", "No service class found"))
    else:
        bases = {base.id for base in service.bases if isinstance(base, ast.Name)}
        if rule_values.get("service.base_class") not in bases:
            findings.append(ValidationFinding("service.base_class", "Service does not extend required base class"))
        decorators = {d.id for d in service.decorator_list if isinstance(d, ast.Name)}
        if rule_values.get("service.required_decorator") not in decorators:
            findings.append(ValidationFinding("service.required_decorator", "Service lacks required decorator"))
    if rule_values.get("logging.required_call") and "logger.info(" not in source:
        findings.append(ValidationFinding("logging.required_call", "Required logger.info call not found"))
    if "print(" in source:
        findings.append(ValidationFinding("logging.forbidden_print", "print() is forbidden"))
    return ValidationReport(passed=not findings, findings=tuple(findings))
