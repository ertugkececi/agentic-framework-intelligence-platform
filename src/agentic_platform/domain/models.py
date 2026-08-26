"""Typed domain contracts for framework intelligence and retrieval."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping


class RuleOrigin(StrEnum):
    DETERMINISTIC_INFERRED = "deterministic_inferred"
    LLM_INFERRED = "llm_inferred"
    HUMAN_APPROVED = "human_approved"
    HUMAN_EDITED = "human_edited"


class RuleStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Evidence:
    source_path: str
    symbol: str
    observation: str
    polarity: str = "support"


@dataclass(frozen=True)
class FrameworkRule:
    kind: str
    expected_value: str
    confidence: float
    support_count: int
    conflict_count: int
    evidence: tuple[Evidence, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)
    origin: RuleOrigin = RuleOrigin.DETERMINISTIC_INFERRED
    status: RuleStatus = RuleStatus.CANDIDATE
    framework_version: str = "1.0"
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ImportSpec:
    module: str
    symbol: str
    alias: str | None = None

    @property
    def local_name(self) -> str:
        return self.alias or self.symbol


@dataclass(frozen=True)
class CodeExample:
    source_path: str
    symbol: str
    snippet: str
    score: int = 0
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceDependency:
    attribute: str
    class_name: str
    import_module: str | None
    methods: tuple[str, ...]
    constructor_arguments: tuple[str, ...]


@dataclass(frozen=True)
class SourceIndexEntry:
    source_path: str
    symbol: str
    snippet: str
    tokens: tuple[str, ...]
    dependencies: tuple[SourceDependency, ...]


@dataclass(frozen=True)
class SourceIndex:
    entries: tuple[SourceIndexEntry, ...]


@dataclass(frozen=True)
class UnresolvedDependencyCandidate:
    source_path: str
    attribute: str
    class_name: str
    import_module: str | None
    methods: tuple[str, ...]
    constructor_arguments: tuple[str, ...]
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class InvocationRequirement:
    """A learned dependency call whose argument shapes are safe to render."""

    method_name: str
    argument_shapes: tuple[str, ...]
    supported: bool


@dataclass(frozen=True)
class DependencyContext:
    attribute: str
    class_name: str | None
    import_module: str | None
    methods: tuple[str, ...]
    constructor_arguments: tuple[str, ...]
    type_pattern: str | None = None
    required: bool = True
    required_invocations: tuple[InvocationRequirement, ...] = ()


@dataclass(frozen=True)
class CodingContext:
    service_base_class: str
    service_decorator: str
    imports: tuple[ImportSpec, ...]
    dependencies: tuple[DependencyContext, ...]
    examples: tuple[CodeExample, ...]
    unresolved_dependencies: tuple[UnresolvedDependencyCandidate, ...] = ()


@dataclass(frozen=True)
class CommandResult:
    passed: bool
    command: tuple[str, ...]
    output: str
    timed_out: bool = False


@dataclass(frozen=True)
class ValidationFinding:
    rule_kind: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    findings: tuple[ValidationFinding, ...] = ()
