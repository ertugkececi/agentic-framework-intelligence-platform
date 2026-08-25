"""Deterministic Python AST-based framework pattern discovery."""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

from agentic_platform.domain.models import Evidence, FrameworkRule


class FrameworkLearner:
    """Aggregates AST observations; weak patterns remain candidates."""

    def __init__(self, minimum_evidence: int = 3) -> None:
        self.minimum_evidence = minimum_evidence

    def learn(self, repository: Path) -> list[FrameworkRule]:
        observations: dict[str, dict[str, list[Evidence]]] = defaultdict(lambda: defaultdict(list))
        service_count = 0
        for source_path in repository.rglob("*.py"):
            if any(part in {".git", ".venv", "__pycache__"} for part in source_path.parts):
                continue
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            relative = source_path.relative_to(repository).as_posix()
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name.endswith("Service") and node.name != "BaseService":
                    service_count += 1
                    bases = {self._name(base) for base in node.bases}
                    if "BaseService" in bases:
                        observations["service.base_class"]["BaseService"].append(
                            Evidence(relative, node.name, "extends BaseService")
                        )
                    decorators = {self._name(decorator) for decorator in node.decorator_list}
                    if "business_service" in decorators:
                        observations["service.required_decorator"]["business_service"].append(
                            Evidence(relative, node.name, "uses @business_service")
                        )
                    if self._uses_logger_info(node):
                        observations["logging.required_call"]["logger.info"].append(
                            Evidence(relative, node.name, "calls logger.info")
                        )
        rules: list[FrameworkRule] = []
        for kind, by_value in observations.items():
            for expected, evidence in by_value.items():
                support = len(evidence)
                conflicts = max(service_count - support, 0)
                confidence = support / service_count if service_count else 0.0
                rules.append(FrameworkRule(
                    kind=kind,
                    expected_value=expected,
                    confidence=confidence,
                    support_count=support,
                    conflict_count=conflicts,
                    evidence=tuple(evidence),
                    status="active" if support >= self.minimum_evidence and confidence >= 0.8 else "candidate",
                ))
        return rules

    @staticmethod
    def _name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            return FrameworkLearner._name(node.func)
        return ""

    @staticmethod
    def _uses_logger_info(node: ast.ClassDef) -> bool:
        for descendant in ast.walk(node):
            if not isinstance(descendant, ast.Call) or not isinstance(descendant.func, ast.Attribute):
                continue
            receiver = descendant.func.value
            if descendant.func.attr != "info":
                continue
            if isinstance(receiver, ast.Name) and receiver.id == "logger":
                return True
            if isinstance(receiver, ast.Attribute) and receiver.attr == "logger":
                return True
        return False
