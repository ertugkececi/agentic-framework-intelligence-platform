"""Deterministic Python AST-based framework pattern discovery."""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

from agentic_platform.domain.models import Evidence, FrameworkRule, RuleStatus


class FrameworkLearner:
    """Learns repeated service structures without knowing customer symbols."""

    def __init__(self, minimum_evidence: int = 3) -> None:
        self.minimum_evidence = minimum_evidence

    def learn(self, repository: Path) -> list[FrameworkRule]:
        observations: dict[str, dict[tuple[str, str], list[Evidence]]] = defaultdict(lambda: defaultdict(list))
        service_count = 0
        for source_path in repository.rglob("*.py"):
            if any(part in {".git", ".venv", "__pycache__", "tests"} for part in source_path.parts):
                continue
            source = source_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(source_path))
            relative = source_path.relative_to(repository).as_posix()
            imports = self._imports(tree)
            for service in (
                node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name.endswith("Service")
                and (node.bases or node.decorator_list)
            ):
                service_count += 1
                self._observe_service_structure(observations, service, relative, imports)
        return self._aggregate(observations, service_count)

    def _observe_service_structure(
        self,
        observations: dict[str, dict[tuple[str, str], list[Evidence]]],
        service: ast.ClassDef,
        relative: str,
        imports: dict[str, str],
    ) -> None:
        for base in service.bases:
            symbol = self._name(base)
            if symbol:
                self._record(observations, "service.base_class", symbol, imports, relative, service.name, f"extends {symbol}")
        for decorator in service.decorator_list:
            symbol = self._name(decorator)
            if symbol:
                self._record(observations, "service.required_decorator", symbol, imports, relative, service.name, f"uses @{symbol}")

        dependencies = self._constructor_dependencies(service)
        for attribute, dependency in dependencies.items():
            self._record(observations, "logging.logger_class", dependency, imports, relative, service.name, f"assigns self.{attribute}")
            self._record(observations, "logging.logger_attribute", attribute, {}, relative, service.name, f"uses self.{attribute}")
            for method in self._methods_called_on(service, attribute):
                self._record(observations, "logging.required_method", method, {}, relative, service.name, f"calls self.{attribute}.{method}")

    def _aggregate(
        self,
        observations: dict[str, dict[tuple[str, str], list[Evidence]]],
        service_count: int,
    ) -> list[FrameworkRule]:
        rules: list[FrameworkRule] = []
        for kind, by_value in observations.items():
            for (expected_value, module), evidence in by_value.items():
                support = len(evidence)
                confidence = support / service_count if service_count else 0.0
                rules.append(FrameworkRule(
                    kind=kind,
                    expected_value=expected_value,
                    confidence=confidence,
                    support_count=support,
                    conflict_count=max(service_count - support, 0),
                    evidence=tuple(evidence),
                    metadata={"import_module": module} if module else {},
                    status=RuleStatus.ACTIVE if support >= self.minimum_evidence and confidence >= 0.8 else RuleStatus.CANDIDATE,
                ))
        return rules

    @staticmethod
    def _record(
        observations: dict[str, dict[tuple[str, str], list[Evidence]]],
        kind: str,
        value: str,
        imports: dict[str, str],
        path: str,
        service: str,
        observation: str,
    ) -> None:
        observations[kind][(value, imports.get(value, ""))].append(Evidence(path, service, observation))

    @staticmethod
    def _imports(tree: ast.Module) -> dict[str, str]:
        imports: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name.split(".")[0]] = alias.name
        return imports

    @staticmethod
    def _constructor_dependencies(service: ast.ClassDef) -> dict[str, str]:
        dependencies: dict[str, str] = {}
        initializer = next((node for node in service.body if isinstance(node, ast.FunctionDef) and node.name == "__init__"), None)
        if initializer is None:
            return dependencies
        for node in ast.walk(initializer):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            if not isinstance(node.value.func, ast.Name):
                continue
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    dependencies[target.attr] = node.value.func.id
        return dependencies

    @staticmethod
    def _methods_called_on(service: ast.ClassDef, attribute: str) -> set[str]:
        methods: set[str] = set()
        for node in ast.walk(service):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            receiver = node.func.value
            if isinstance(receiver, ast.Attribute) and isinstance(receiver.value, ast.Name):
                if receiver.value.id == "self" and receiver.attr == attribute:
                    methods.add(node.func.attr)
        return methods

    @staticmethod
    def _name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            return FrameworkLearner._name(node.func)
        return ""
