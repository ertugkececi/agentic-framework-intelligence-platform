from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import pytest

from agentic_platform.domain.models import FrameworkRule, KnowledgeScope, RuleStatus
from agentic_platform.retrieval.assembly import assemble_coding_context
from agentic_platform.retrieval.semantic_chunks import ChunkKind, SemanticChunk
from agentic_platform.retrieval.semantic_store import SemanticMatch, VectorEntry
from agentic_platform.tasks.types import DevelopmentTask


def scope() -> KnowledgeScope:
    return KnowledgeScope("tenant", "framework", "4.0", "project", "module")


def active_rule(kind: str, value: str, metadata: dict[str, object]) -> FrameworkRule:
    return FrameworkRule(kind, value, 1.0, 3, 0, (), metadata=metadata, status=RuleStatus.ACTIVE, scope=scope())


@dataclass
class RecordingRuleStore:
    rules: list[FrameworkRule]
    calls: list[tuple[str, KnowledgeScope | None]] = field(default_factory=list)

    def active_rules_for(self, prefix: str, *, scope: KnowledgeScope | None = None) -> list[FrameworkRule]:
        self.calls.append((prefix, scope))
        return [rule for rule in self.rules if rule.kind.startswith(prefix + ".")]


@dataclass
class SemanticStore:
    matches: tuple[SemanticMatch, ...]
    calls: list[tuple[KnowledgeScope, tuple[float, ...], int, ChunkKind | str | None]] = field(default_factory=list)

    def upsert(self, entries: Sequence[VectorEntry]) -> None:
        raise AssertionError("assembly must not write vectors")

    def delete_source(self, requested_scope: KnowledgeScope, source_path: str) -> None:
        raise AssertionError("assembly must not delete vectors")

    def search(self, requested_scope, query_vector, *, limit, kind=None):
        self.calls.append((requested_scope, tuple(query_vector), limit, kind))
        return self.matches


def test_assembles_scoped_rules_semantic_examples_and_dependencies(tmp_path) -> None:
    repository = tmp_path / "repo"
    (repository / "app").mkdir(parents=True)
    (repository / "app/example.py").write_text(
        "from app.dependencies import SharedClient\n"
        "from app.framework import BaseArtifact, registered\n"
        "@registered\n"
        "class ExampleArtifact(BaseArtifact):\n"
        "    def __init__(self):\n"
        "        self.client = SharedClient()\n",
        encoding="utf-8",
    )
    rules = [
        active_rule("service.base_class", "BaseArtifact", {"import_module": "app.framework"}),
        active_rule("service.required_decorator", "registered", {"import_module": "app.framework"}),
        active_rule("dependency.constructor", "client", {
            "concrete_types": ["SharedClient"],
            "import_modules": ["app.dependencies"],
            "concrete_imports": {"SharedClient": {"symbol": "SharedClient", "alias": None}},
            "usage_methods": [],
            "constructor_arguments": [],
            "required_invocations": [],
        }),
    ]
    rule_store = RecordingRuleStore(rules)
    semantic_chunk = SemanticChunk.create(
        scope=scope(), source_path="app/example.py", kind=ChunkKind.SOURCE,
        content="class ExampleArtifact: ...", start_line=1, end_line=1,
        repository_revision="revision", language_id="python", symbol="ExampleArtifact",
    )
    semantic_store = SemanticStore((SemanticMatch(semantic_chunk, 0.91),))

    resolved_rules, context = assemble_coding_context(
        rule_store, semantic_store, scope(), repository,
        DevelopmentTask("service", "NewArtifact", ()), (0.2, 0.4), example_limit=2,
    )

    assert resolved_rules == rules
    assert context.structure.base_classes == ("BaseArtifact",)
    assert [(item.attribute, item.class_name) for item in context.dependencies] == [("client", "SharedClient")]
    assert [(item.symbol, item.score) for item in context.examples] == [("ExampleArtifact", 0.91)]
    assert rule_store.calls == [("service", scope()), ("dependency", scope())]
    assert semantic_store.calls == [(scope(), (0.2, 0.4), 6, ChunkKind.SOURCE)]


def test_fails_closed_when_structured_store_returns_cross_scope_rule(tmp_path) -> None:
    other = KnowledgeScope("other", "framework", "4.0", "project", "module")
    rules = [
        FrameworkRule("controller.base_class", "BaseArtifact", 1.0, 3, 0, (),
                      metadata={"import_module": "app.framework"},
                      status=RuleStatus.ACTIVE, scope=other),
        active_rule("controller.required_decorator", "registered", {"import_module": "app.framework"}),
    ]
    repository = tmp_path / "repo"
    repository.mkdir()
    semantic_store = SemanticStore(())

    with pytest.raises(ValueError, match="rule scope mismatch"):
        assemble_coding_context(
            RecordingRuleStore(rules), semantic_store, scope(), repository,
            DevelopmentTask("controller", "NewArtifact", ()), (0.2,),
        )

    assert semantic_store.calls == []
