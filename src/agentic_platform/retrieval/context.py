"""Task-aware rule, import, dependency and representative-example assembly."""
from __future__ import annotations

import ast
from pathlib import Path

from agentic_platform.domain.models import CodeExample, CodingContext, FrameworkRule, ImportSpec
from agentic_platform.framework_knowledge.sqlite_store import SQLiteKnowledgeStore


def retrieve_service_context(store: SQLiteKnowledgeStore, repository: Path) -> tuple[list[FrameworkRule], CodingContext]:
    rules = store.active_rules_for("service") + store.active_rules_for("logging")
    by_kind = {rule.kind: rule for rule in rules}
    required = {
        "service.base_class", "service.required_decorator", "logging.logger_class",
        "logging.logger_attribute", "logging.required_method",
    }
    missing = required - by_kind.keys()
    if missing:
        raise ValueError(f"Missing active framework rules: {', '.join(sorted(missing))}")
    imports = tuple(
        ImportSpec(rule.metadata["import_module"], rule.expected_value)
        for kind in ("service.base_class", "service.required_decorator", "logging.logger_class")
        if (rule := by_kind[kind]).metadata.get("import_module")
    )
    examples = tuple(_representative_examples(repository, rules))
    return rules, CodingContext(
        service_base_class=by_kind["service.base_class"].expected_value,
        service_decorator=by_kind["service.required_decorator"].expected_value,
        imports=imports,
        logger_class=by_kind["logging.logger_class"].expected_value,
        logger_attribute=by_kind["logging.logger_attribute"].expected_value,
        logger_method=by_kind["logging.required_method"].expected_value,
        examples=examples,
    )


def _representative_examples(repository: Path, rules: list[FrameworkRule]) -> list[CodeExample]:
    paths = sorted({rule.evidence[0].source_path for rule in rules if rule.evidence})
    examples: list[CodeExample] = []
    for relative in paths[:3]:
        source_path = repository / relative
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
        service = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith("Service"))
        examples.append(CodeExample(relative, service.name, ast.get_source_segment(source, service) or ""))
    return examples
