"""Deterministic AST compliance checks for active framework rules."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable

from agentic_platform.domain.models import FrameworkRule, ImportSpec, ValidationFinding, ValidationReport


def validate_service(source_path: Path, rules: list[FrameworkRule]) -> ValidationReport:
    """Validate generated source against active learned structure and dependency rules."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    service = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith("Service")),
        None,
    )
    if service is None:
        return ValidationReport(False, (ValidationFinding("service.class", "Service class missing"),))

    findings: list[ValidationFinding] = []
    imports = _imports(tree)
    _validate_service_structure(service, imports, rules, findings)
    _validate_resolved_dependencies(service, imports, rules, findings)
    return ValidationReport(not findings, tuple(findings))


def _validate_service_structure(
    service: ast.ClassDef,
    imports: dict[str, ImportSpec],
    rules: Iterable[FrameworkRule],
    findings: list[ValidationFinding],
) -> None:
    for kind, nodes in (
        ("service.base_class", service.bases),
        ("service.required_decorator", service.decorator_list),
    ):
        rule = next((item for item in rules if item.kind == kind), None)
        if rule is None:
            continue
        observed = {_name(node) for node in nodes}
        if rule.expected_value not in observed:
            findings.append(ValidationFinding(kind, "Required service structure missing"))
            continue
        if not _matches_import_provenance(imports, rule.expected_value, rule.metadata):
            findings.append(
                ValidationFinding(kind, f"Required import provenance missing for {rule.expected_value}")
            )


def _validate_resolved_dependencies(
    service: ast.ClassDef,
    imports: dict[str, ImportSpec],
    rules: Iterable[FrameworkRule],
    findings: list[ValidationFinding],
) -> None:
    assignments = _dependency_assignments(service)
    for rule in (item for item in rules if item.kind == "dependency.constructor"):
        concrete_types = tuple(rule.metadata.get("concrete_types", ()))
        import_modules = tuple(rule.metadata.get("import_modules", ()))
        if len(concrete_types) != 1:
            continue

        attribute = rule.expected_value
        class_name = concrete_types[0]
        assignment = assignments.get(attribute)
        if assignment is None:
            findings.append(ValidationFinding("dependency.constructor", f"Resolved dependency missing: {attribute}"))
            continue
        if _name(assignment.func) != class_name:
            findings.append(
                ValidationFinding("dependency.constructor", f"Resolved dependency type mismatch: {attribute}")
            )
            continue
        import_metadata = rule.metadata.get("concrete_imports", {}).get(class_name, {})
        if import_modules and not _matches_import_provenance(imports, class_name, import_metadata):
            findings.append(
                ValidationFinding(
                    "dependency.constructor",
                    f"Resolved dependency import provenance missing: {class_name}",
                )
            )
        expected_arguments = tuple(rule.metadata.get("constructor_arguments", ()))
        observed_arguments = tuple(_constructor_argument(argument) for argument in assignment.args)
        if observed_arguments != expected_arguments:
            findings.append(
                ValidationFinding(
                    "dependency.constructor",
                    f"Resolved dependency constructor arguments mismatch: {attribute}",
                )
            )
        _validate_invocations(service, attribute, rule, findings)


def _validate_invocations(
    service: ast.ClassDef,
    attribute: str,
    rule: FrameworkRule,
    findings: list[ValidationFinding],
) -> None:
    requirements = tuple(rule.metadata.get("required_invocations", ()))
    if not requirements:
        return
    operations = [
        node
        for node in service.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != "__init__"
    ]
    for requirement in requirements:
        method_name = requirement["method_name"]
        argument_shapes = tuple(requirement["argument_shapes"])
        if not requirement["supported"]:
            findings.append(
                ValidationFinding(
                    "dependency.invocation",
                    f"Unsupported required dependency invocation: {attribute}.{method_name}",
                )
            )
            continue
        for operation in operations:
            if not _has_invocation(operation, attribute, method_name, argument_shapes):
                findings.append(
                    ValidationFinding(
                        "dependency.invocation",
                        f"Required dependency invocation missing or malformed: {attribute}.{method_name} in {operation.name}",
                    )
                )


def _dependency_assignments(service: ast.ClassDef) -> dict[str, ast.Call]:
    assignments: dict[str, ast.Call] = {}
    for node in ast.walk(service):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                assignments[target.attr] = node.value
    return assignments


def _has_invocation(
    operation: ast.FunctionDef | ast.AsyncFunctionDef,
    attribute: str,
    method_name: str,
    argument_shapes: tuple[str, ...],
) -> bool:
    for node in ast.walk(operation):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == method_name
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "self"
            and node.func.value.attr == attribute
        ):
            continue
        if tuple(_invocation_shape(argument) for argument in node.args) == argument_shapes:
            return True
    return False


def _imports(tree: ast.Module) -> dict[str, ImportSpec]:
    return {
        alias.asname or alias.name: ImportSpec(node.module, alias.name, alias.asname)
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    }


def _matches_import_provenance(
    imports: dict[str, ImportSpec],
    local_name: str,
    metadata: object,
) -> bool:
    if not isinstance(metadata, dict):
        return True
    expected_module = metadata.get("import_module", metadata.get("module"))
    if not expected_module:
        return True
    imported = imports.get(local_name)
    return (
        imported is not None
        and imported.module == expected_module
        and imported.symbol == metadata.get("import_symbol", metadata.get("symbol", local_name))
        and imported.alias == metadata.get("import_alias", metadata.get("alias"))
    )


def _constructor_argument(argument: ast.expr) -> str:
    if isinstance(argument, ast.Name) and argument.id == "__name__":
        return "__name__"
    if isinstance(argument, ast.Constant):
        return repr(argument.value)
    return "unsupported"


def _invocation_shape(argument: ast.expr) -> str:
    if isinstance(argument, ast.Constant):
        if isinstance(argument.value, str):
            return "string_literal"
        if isinstance(argument.value, bool):
            return "boolean_literal"
        if isinstance(argument.value, int):
            return "integer_literal"
        if isinstance(argument.value, float):
            return "float_literal"
        if argument.value is None:
            return "none_literal"
    if isinstance(argument, ast.Dict) and not argument.keys:
        return "empty_mapping"
    if isinstance(argument, (ast.List, ast.Tuple)) and not argument.elts:
        return "empty_sequence"
    return "unsupported"


def _name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
