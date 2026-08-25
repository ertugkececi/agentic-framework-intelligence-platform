"""Task-aware context selection: rules, examples and dependency paths."""
from __future__ import annotations

from pathlib import Path

from agentic_platform.domain.models import FrameworkRule
from agentic_platform.framework_knowledge.sqlite_store import SQLiteKnowledgeStore


def retrieve_service_context(store: SQLiteKnowledgeStore, repository: Path) -> tuple[list[FrameworkRule], list[str], list[str]]:
    rules = store.active_rules_for("service") + store.active_rules_for("logging")
    examples: list[str] = []
    for rule in rules:
        if rule.evidence:
            examples.append(rule.evidence[0].source_path)
    dependencies = ["app/framework.py"] if (repository / "app" / "framework.py").exists() else []
    return rules, sorted(set(examples)), dependencies
