"""Deterministic AST compliance checks for active framework rules."""
from __future__ import annotations
import ast
from pathlib import Path
from agentic_platform.domain.models import FrameworkRule, ValidationFinding, ValidationReport

def validate_service(source_path: Path, rules: list[FrameworkRule]) -> ValidationReport:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    service = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith("Service")), None)
    if service is None:
        return ValidationReport(False, (ValidationFinding("service.class", "Service class missing"),))
    findings: list[ValidationFinding] = []
    _validate_service_structure(service, rules, findings)
    _validate_resolved_dependencies(service, rules, findings)
    return ValidationReport(not findings, tuple(findings))

def _validate_service_structure(service, rules, findings) -> None:
    for kind, nodes in (("service.base_class", service.bases), ("service.required_decorator", service.decorator_list)):
        expected = next((rule.expected_value for rule in rules if rule.kind == kind), None)
        observed = {getattr(node, "id", "") for node in nodes}
        if expected and expected not in observed:
            findings.append(ValidationFinding(kind, "Required service structure missing"))

def _validate_resolved_dependencies(service, rules, findings) -> None:
    assignments = {(target.attr, getattr(node.value.func, "id", "")) for node in ast.walk(service) if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) for target in node.targets if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self"}
    for rule in (item for item in rules if item.kind == "dependency.constructor"):
        types = rule.metadata.get("concrete_types", [])
        if len(types) == 1 and (rule.expected_value, types[0]) not in assignments:
            findings.append(ValidationFinding("dependency.constructor", "Resolved dependency missing"))
