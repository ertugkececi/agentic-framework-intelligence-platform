"""Production boundary for assembling bounded, scoped coding context."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from agentic_platform.domain.models import CodingContext, FrameworkRule, KnowledgeScope
from agentic_platform.framework_knowledge.store import RuleKnowledgeStore
from agentic_platform.retrieval.context import (
    retrieve_controller_context,
    retrieve_service_context,
)
from agentic_platform.retrieval.example_mining import mine_representative_examples
from agentic_platform.retrieval.semantic_store import SemanticVectorStore
from agentic_platform.tasks.types import DevelopmentTask


def assemble_coding_context(
    rule_store: RuleKnowledgeStore,
    semantic_store: SemanticVectorStore,
    scope: KnowledgeScope,
    repository: Path,
    task: DevelopmentTask,
    query_vector: Sequence[float],
    *,
    example_limit: int = 6,
) -> tuple[list[FrameworkRule], CodingContext]:
    """Combine scoped rules, dependencies, and semantic examples.

    Structured rules remain authoritative for artifact structure and dependency
    constraints. Semantic retrieval supplies only representative examples and
    cannot weaken the rule-derived context.
    """
    if task.artifact_type == "controller":
        rules, rule_context = retrieve_controller_context(
            rule_store, repository, task, scope=scope
        )
    elif task.artifact_type == "service":
        rules, rule_context = retrieve_service_context(
            rule_store, repository, task, scope=scope
        )
    else:
        raise ValueError(f"unsupported artifact family: {task.artifact_type}")

    if any(rule.scope != scope for rule in rules):
        raise ValueError("structured rule scope mismatch")

    examples = mine_representative_examples(
        semantic_store, scope, query_vector, limit=example_limit
    )
    return rules, CodingContext(
        structure=rule_context.structure,
        examples=examples,
        unresolved_dependencies=rule_context.unresolved_dependencies,
    )
