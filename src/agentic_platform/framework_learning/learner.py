"""Generic AST learning of repeated service structures and dependency calls."""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Iterable

from agentic_platform.domain.models import Evidence, FrameworkRule, ImportSpec, RuleStatus


_SUPPORTED_ARGUMENT_SHAPES = {
    "string_literal",
    "integer_literal",
    "float_literal",
    "boolean_literal",
    "none_literal",
    "empty_mapping",
    "empty_sequence",
}


class FrameworkLearner:
    """Infer active conventions solely from repeated structural source evidence."""

    def __init__(self, minimum_evidence: int = 3, active_threshold: float = 0.8) -> None:
        self.minimum_evidence = minimum_evidence
        self.active_threshold = active_threshold

    def learn(self, repository: Path) -> list[FrameworkRule]:
        observations: DefaultDict[str, DefaultDict[object, list[object]]] = defaultdict(lambda: defaultdict(list))
        service_count = 0
        for path in sorted(repository.rglob("*.py")):
            if "tests" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports = self._imports(tree)
            relative_path = path.relative_to(repository).as_posix()
            for service in self._services(tree):
                service_count += 1
                self._observe(observations, service, imports, relative_path)
        return self._rules(observations, service_count)

    @staticmethod
    def _services(tree: ast.Module) -> list[ast.ClassDef]:
        return [
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name.endswith("Service") and (node.bases or node.decorator_list)
        ]

    def _observe(
        self,
        observations: DefaultDict[str, DefaultDict[object, list[object]]],
        service: ast.ClassDef,
        imports: dict[str, ImportSpec],
        source_path: str,
    ) -> None:
        for kind, nodes in (
            ("service.base_class", service.bases),
            ("service.required_decorator", service.decorator_list),
        ):
            for node in nodes:
                name = self._name(node)
                imported = imports.get(name)
                if name:
                    observations[kind][(
                        name,
                        imported.module if imported else "",
                        imported.symbol if imported else name,
                        imported.alias if imported else None,
                    )].append(
                        Evidence(source_path, service.name, name)
                    )

        for attribute, (class_name, arguments) in self._dependencies(service).items():
            invocations = self._calls(service, attribute)
            observations["dependency.constructor"][attribute].append(
                (
                    Evidence(source_path, service.name, attribute),
                    class_name,
                    imports.get(class_name),
                    arguments,
                    invocations,
                )
            )

    def _rules(
        self,
        observations: DefaultDict[str, DefaultDict[object, list[object]]],
        service_count: int,
    ) -> list[FrameworkRule]:
        rules: list[FrameworkRule] = []
        for kind, values in observations.items():
            for key, entries in values.items():
                if kind == "dependency.constructor":
                    rule = self._dependency_rule(str(key), entries, service_count)
                else:
                    rule = self._structure_rule(kind, key, entries, service_count)
                rules.append(rule)
        return rules

    def _dependency_rule(self, attribute: str, entries: list[object], service_count: int) -> FrameworkRule:
        dependency_entries = list(entries)
        evidence = tuple(entry[0] for entry in dependency_entries)
        concrete_types = sorted({entry[1] for entry in dependency_entries})
        import_modules = sorted({entry[2].module for entry in dependency_entries if entry[2] is not None})
        constructor_argument_shapes = sorted({entry[3] for entry in dependency_entries})
        invocations = sorted({invocation for entry in dependency_entries for invocation in entry[4]})
        required_invocations = [
            self._invocation_requirement(invocation, dependency_entries, service_count)
            for invocation in invocations
        ]
        metadata = {
            "concrete_types": concrete_types,
            "import_modules": import_modules,
            "constructor_arguments": constructor_argument_shapes[0] if len(constructor_argument_shapes) == 1 else (),
            "usage_methods": sorted({method_name for method_name, _ in invocations}),
            "required_invocations": [item for item in required_invocations if item["active"]],
            "invocation_evidence": required_invocations,
            "concrete_imports": {
                entry[1]: self._import_metadata(entry[2])
                for entry in dependency_entries
                if entry[2] is not None
            },
            "type_pattern": self._suffix(concrete_types),
        }
        return self._rule("dependency.constructor", attribute, evidence, metadata, service_count)

    def _invocation_requirement(
        self,
        invocation: tuple[str, tuple[str, ...]],
        entries: list[object],
        service_count: int,
    ) -> dict[str, object]:
        method_name, argument_shapes = invocation
        evidence = [entry[0] for entry in entries if invocation in entry[4]]
        support_count = len(evidence)
        confidence = support_count / service_count if service_count else 0.0
        active = support_count >= self.minimum_evidence and confidence >= self.active_threshold
        return {
            "method_name": method_name,
            "argument_shapes": list(argument_shapes),
            "supported": all(shape in _SUPPORTED_ARGUMENT_SHAPES for shape in argument_shapes),
            "support_count": support_count,
            "conflict_count": service_count - support_count,
            "confidence": confidence,
            "evidence": [item.__dict__ for item in evidence],
            "active": active,
        }

    def _structure_rule(
        self,
        kind: str,
        key: object,
        entries: list[object],
        service_count: int,
    ) -> FrameworkRule:
        expected_value, import_module, import_symbol, import_alias = key
        metadata = (
            {"import_module": import_module, "import_symbol": import_symbol, "import_alias": import_alias}
            if import_module
            else {}
        )
        return self._rule(kind, expected_value, tuple(entries), metadata, service_count)

    def _rule(
        self,
        kind: str,
        expected_value: str,
        evidence: tuple[Evidence, ...],
        metadata: dict[str, object],
        service_count: int,
    ) -> FrameworkRule:
        support_count = len(evidence)
        confidence = support_count / service_count if service_count else 0.0
        status = (
            RuleStatus.ACTIVE
            if support_count >= self.minimum_evidence and confidence >= self.active_threshold
            else RuleStatus.CANDIDATE
        )
        return FrameworkRule(
            kind=kind,
            expected_value=expected_value,
            confidence=confidence,
            support_count=support_count,
            conflict_count=service_count - support_count,
            evidence=evidence,
            metadata=metadata,
            status=status,
        )

    @staticmethod
    def _dependencies(service: ast.ClassDef) -> dict[str, tuple[str, tuple[str, ...]]]:
        dependencies: dict[str, tuple[str, tuple[str, ...]]] = {}
        initializer = next(
            (node for node in service.body if isinstance(node, ast.FunctionDef) and node.name == "__init__"),
            None,
        )
        for node in ast.walk(initializer) if initializer else ():
            if not (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
            ):
                continue
            arguments = tuple(FrameworkLearner._constructor_argument(argument) for argument in node.value.args)
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    dependencies[target.attr] = (node.value.func.id, arguments)
        return dependencies

    @staticmethod
    def _calls(service: ast.ClassDef, attribute: str) -> set[tuple[str, tuple[str, ...]]]:
        calls: set[tuple[str, tuple[str, ...]]] = set()
        for node in ast.walk(service):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "self"
                and node.func.value.attr == attribute
            ):
                continue
            calls.add((node.func.attr, tuple(FrameworkLearner._invocation_shape(argument) for argument in node.args)))
        return calls

    @staticmethod
    def _constructor_argument(argument: ast.expr) -> str:
        if isinstance(argument, ast.Name) and argument.id == "__name__":
            return "__name__"
        if isinstance(argument, ast.Constant):
            return repr(argument.value)
        return "unsupported"

    @staticmethod
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

    @staticmethod
    def _imports(tree: ast.Module) -> dict[str, ImportSpec]:
        return {
            alias.asname or alias.name: ImportSpec(node.module, alias.name, alias.asname)
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        }

    @staticmethod
    def _import_metadata(imported: ImportSpec) -> dict[str, str | None]:
        return {"module": imported.module, "symbol": imported.symbol, "alias": imported.alias}

    @staticmethod
    def _suffix(types: Iterable[str]) -> str | None:
        values = list(types)
        if len(values) < 2:
            return None
        suffix = values[0]
        for value in values[1:]:
            while suffix and not value.endswith(suffix):
                suffix = suffix[1:]
        return f"*{suffix}" if len(suffix) >= 4 and suffix[0].isupper() else None

    @staticmethod
    def _name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""
